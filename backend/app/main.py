"""Dataful API (see API.md for the contract). Routes stay thin; logic lives in service/views/issues."""

from __future__ import annotations

import logging
import tempfile
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(BACKEND_DIR.parent / ".env")  # also accept a key in the repo root .env

from . import ai, chat, issues, loader, ops, persist, service, store, views  # noqa: E402  (env must load first)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("dataful")

View = Literal["original", "decisions"]


def _warm(datasets: list[store.DatasetState]) -> None:
    """Profile + detect in the background so the first click is instant."""
    for ds in sorted(datasets, key=lambda d: d.rows):
        try:
            issues.warm(ds)
            service.profile_json(ds, "decisions")
        except Exception:  # noqa: BLE001 - warming is best effort
            log.exception("warming %s failed", ds.id)


def _load_saved_uploads() -> None:
    for path, filename in persist.saved_uploads():
        try:
            loader.load_upload(path.read_bytes(), filename)
        except Exception:  # noqa: BLE001 - one bad saved file must not stop startup
            log.exception("could not reload saved upload %s", path.name)


@asynccontextmanager
async def lifespan(_: FastAPI):
    loader.load_demos()
    _load_saved_uploads()
    for ds in store.DATASETS.values():
        persist.load(ds)
    log.info("loaded %d datasets; AI %s", len(store.DATASETS), "on" if ai.enabled() else "off")
    threading.Thread(target=_warm, args=(list(store.DATASETS.values()),), daemon=True).start()
    yield


app = FastAPI(title="Dataful API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(ops.OpError)
async def op_error(_: Request, exc: ops.OpError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(ai.AIError)
async def ai_error(_: Request, exc: ai.AIError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    """Last resort: every error is still a JSON {"detail"} the UI can show."""
    log.exception("unhandled error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on the server; please try again."})


def _dataset(dataset_id: str) -> store.DatasetState:
    ds = store.get(dataset_id)
    if not ds:
        raise HTTPException(404, f"Dataset '{dataset_id}' not found")
    return ds


class OpBody(BaseModel):
    op: dict[str, Any]
    issue_id: str | None = None     # previewing a new answer to an already-answered issue


class DecisionBody(BaseModel):
    op: dict[str, Any] | None
    issue_id: str | None = None
    reason: str | None = None


class EnabledBody(BaseModel):
    enabled: bool


# ---------- datasets ----------

@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "ai_enabled": ai.enabled(), "model": ai.model_name()}


@app.get("/api/datasets")
def list_datasets() -> list[dict]:
    return [service.dataset_json(ds) for ds in store.DATASETS.values()]


@app.post("/api/datasets/upload")
async def upload(file: UploadFile = File(...)) -> list[dict]:
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "The file is empty")
    try:
        datasets = loader.load_upload(raw, file.filename or "upload.csv")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - unreadable file
        log.exception("upload failed")
        raise HTTPException(400, f"Could not read this file: {exc}") from exc
    if not datasets:
        raise HTTPException(400, "No data found in this file")
    persist.save_upload(raw, file.filename or "upload.csv")
    for ds in datasets:
        persist.save(ds)  # a new upload starts clean, even if an old decisions file used this id
    threading.Thread(target=_warm, args=(datasets,), daemon=True).start()
    return [service.dataset_json(ds) for ds in datasets]


@app.get("/api/datasets/{dataset_id}/profile")
def get_profile(dataset_id: str, view: View = "decisions") -> dict:
    return service.profile_json(_dataset(dataset_id), view)


# ---------- issues ----------

@app.get("/api/datasets/{dataset_id}/issues")
def list_issues(dataset_id: str) -> list[dict]:
    return issues.all_json(_dataset(dataset_id))


@app.post("/api/datasets/{dataset_id}/issues/{issue_id}/skip")
def skip_issue(dataset_id: str, issue_id: str) -> dict:
    ds = _dataset(dataset_id)
    issue = issues.find(ds, issue_id)
    if not issue:
        raise HTTPException(404, f"Issue '{issue_id}' not found")
    return service.skip_issue(ds, issue)


@app.post("/api/datasets/{dataset_id}/review")
def review(dataset_id: str) -> dict:
    if not ai.enabled():
        raise HTTPException(409, "AI review needs ANTHROPIC_API_KEY in backend/.env")
    return service.review(_dataset(dataset_id))


class ChatBody(BaseModel):
    message: str


@app.get("/api/datasets/{dataset_id}/chat")
def chat_history(dataset_id: str) -> dict:
    return {"log": chat.history(_dataset(dataset_id)), "ai_enabled": ai.enabled()}


@app.post("/api/datasets/{dataset_id}/chat")
def chat_send(dataset_id: str, body: ChatBody) -> dict:
    if not ai.enabled():
        raise HTTPException(409, "Chat needs ANTHROPIC_API_KEY in .env")
    return chat.send(_dataset(dataset_id), body.message)


@app.delete("/api/datasets/{dataset_id}/chat")
def chat_reset(dataset_id: str) -> dict:
    chat.reset(_dataset(dataset_id))
    return {"log": []}


# ---------- grid ----------

@app.get("/api/datasets/{dataset_id}/rows")
def get_rows(dataset_id: str, offset: int = 0, limit: int = 100, sort: str | None = None,
             dir: Literal["asc", "desc"] = "asc", filters: str | None = None, search: str | None = None,
             issue_id: str | None = None, view: View = "decisions") -> dict:
    return service.rows_json(_dataset(dataset_id), view, offset, limit, sort, dir, filters, search, issue_id)


@app.get("/api/datasets/{dataset_id}/group")
def get_group(dataset_id: str, by: str, measure: str | None = None,
              agg: Literal["count", "sum", "avg", "count_distinct"] = "count",
              use_count_unit: bool = False, view: View = "decisions", filters: str | None = None) -> dict:
    return service.group_json(_dataset(dataset_id), view, by, measure, agg, use_count_unit, filters)


@app.post("/api/datasets/{dataset_id}/preview")
def preview(dataset_id: str, body: OpBody) -> dict:
    ds = _dataset(dataset_id)
    replacing = issues.decision_for(ds, body.issue_id) if body.issue_id else None
    return views.preview(ds, body.op, replacing)


# ---------- decisions ----------

@app.get("/api/datasets/{dataset_id}/decisions")
def list_decisions(dataset_id: str) -> list[dict]:
    return [d.to_json() for d in _dataset(dataset_id).decisions]


@app.post("/api/datasets/{dataset_id}/decisions")
def add_decision(dataset_id: str, body: DecisionBody) -> dict:
    return service.add_decision(_dataset(dataset_id), body.op, body.issue_id, body.reason).to_json()


def _decision(ds: store.DatasetState, decision_id: str) -> store.Decision:
    decision = service.find_decision(ds, decision_id)
    if not decision:
        raise HTTPException(404, f"Decision '{decision_id}' not found")
    return decision


@app.patch("/api/datasets/{dataset_id}/decisions/{decision_id}")
def patch_decision(dataset_id: str, decision_id: str, body: EnabledBody) -> dict:
    ds = _dataset(dataset_id)
    return service.set_enabled(ds, _decision(ds, decision_id), body.enabled).to_json()


@app.delete("/api/datasets/{dataset_id}/decisions/{decision_id}")
def delete_decision(dataset_id: str, decision_id: str) -> dict:
    ds = _dataset(dataset_id)
    service.remove_decision(ds, _decision(ds, decision_id))
    return {"ok": True}


@app.post("/api/datasets/{dataset_id}/reset")
def reset(dataset_id: str) -> dict:
    service.reset(_dataset(dataset_id))
    return {"ok": True}


# ---------- export ----------

_EXPORT_DIR = Path(tempfile.mkdtemp(prefix="dataful-export-"))


@app.get("/api/datasets/{dataset_id}/export.csv")
def export_csv(dataset_id: str, view: View = "decisions") -> FileResponse:
    ds = _dataset(dataset_id)
    suffix = "clean" if view == "decisions" else "original"
    path = _EXPORT_DIR / f"{ds.id}-{suffix}.csv"
    views.export_csv(views.get_view(ds, view), path)
    return FileResponse(path, media_type="text/csv", filename=path.name)


@app.get("/api/datasets/{dataset_id}/decisions.json")
def export_decisions(dataset_id: str) -> JSONResponse:
    ds = _dataset(dataset_id)
    return JSONResponse(service.decisions_file(ds),
                        headers={"Content-Disposition": f'attachment; filename="{ds.id}-decisions.json"'})
