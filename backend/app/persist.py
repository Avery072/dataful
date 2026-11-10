"""Saved state on disk: each dataset's decisions, and copies of uploaded files.

    backend/data/decisions/{dataset_id}.json   written after every change (temp file + rename)
    backend/data/uploads/{seq}-{file name}     re-loaded at startup, in upload order

Loading is defensive: an unreadable file or a malformed decision is logged and skipped (the
file is kept aside), so saved state can never make a dataset unloadable.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path

from . import store

log = logging.getLogger("dataful.persist")

DATA_DIR = Path(os.environ.get("DATAFUL_DATA_DIR") or Path(__file__).resolve().parents[1] / "data")
FORMAT_VERSION = 1


def decisions_dir() -> Path:
    return DATA_DIR / "decisions"


def uploads_dir() -> Path:
    return DATA_DIR / "uploads"


def _decisions_path(dataset_id: str) -> Path:
    return decisions_dir() / f"{dataset_id}.json"


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# ---------- decisions ----------

def save(ds: store.DatasetState) -> None:
    """Write the dataset's decisions and skipped issues. Never raises: saving is best effort."""
    state = {
        "format": FORMAT_VERSION, "dataset": ds.id, "file": ds.file, "sheet": ds.sheet,
        "next_decision": ds.next_decision, "skipped": sorted(ds.skipped),
        "decisions": [d.to_json() for d in ds.decisions],
    }
    try:
        _atomic_write(_decisions_path(ds.id), json.dumps(state, indent=2).encode("utf-8"))
    except OSError:
        log.exception("could not save decisions for %s", ds.id)


def _decision_from_json(raw: dict, fallback_id: str) -> store.Decision:
    """Rebuild a saved decision. Anything odd about it marks it broken rather than dropping it."""
    op = raw.get("op")
    decision = store.Decision(
        id=raw["id"] if isinstance(raw.get("id"), str) and raw["id"] else fallback_id,
        op=op, plain=str(raw.get("plain") or ""),
        issue_id=raw["issue_id"] if isinstance(raw.get("issue_id"), str) else None,
        reason=raw["reason"] if isinstance(raw.get("reason"), str) else None,
        enabled=raw.get("enabled", True) is True,
        created_at=str(raw.get("created_at") or store.now_iso()),
        broken=raw.get("broken") is True, error=raw.get("error") if isinstance(raw.get("error"), str) else None)
    if op is not None and not isinstance(op, dict):
        decision.mark_broken("The saved operation is not readable")
    return decision


def _set_aside(path: Path) -> None:
    """Keep an unreadable file for inspection instead of overwriting it."""
    try:
        path.replace(path.with_name(f"{path.name}.unreadable-{store.now_iso().replace(':', '')}"))
    except OSError:
        log.exception("could not move %s aside", path)


def load(ds: store.DatasetState) -> None:
    """Restore saved decisions onto a freshly registered dataset (before any view is built)."""
    path = _decisions_path(ds.id)
    if not path.exists():
        return
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict) or not isinstance(state.get("decisions", []), list):
            raise ValueError("not a decisions file")
    except (OSError, ValueError) as exc:
        log.warning("ignoring unreadable decisions file %s: %s", path, exc)
        _set_aside(path)
        return
    decisions = []
    for i, raw in enumerate(state.get("decisions", [])):
        if isinstance(raw, dict):
            decisions.append(_decision_from_json(raw, fallback_id=f"d-restored-{i + 1}"))
        else:
            log.warning("%s: dropping unreadable decision %r", ds.id, raw)
    ds.decisions = decisions
    ds.skipped = {s for s in state.get("skipped", []) if isinstance(s, str)}
    numbers = [int(m.group(1)) for d in decisions if (m := re.fullmatch(r"d(\d+)", d.id))]
    saved_next = state.get("next_decision")
    ds.next_decision = max([saved_next if isinstance(saved_next, int) else 1] + [x + 1 for x in numbers])
    ds.touch()


# ---------- uploads ----------

def save_upload(raw: bytes, filename: str) -> Path:
    """Keep a copy of an uploaded file; the sequence prefix preserves upload order (and dataset ids)."""
    folder = uploads_dir()
    folder.mkdir(parents=True, exist_ok=True)
    seq = 1 + max((int(p.name.split("-", 1)[0]) for p in folder.iterdir() if re.match(r"\d+-", p.name)), default=0)
    safe = re.sub(r"[^\w.\- ]+", "_", Path(filename).name) or "upload.csv"
    path = folder / f"{seq:04d}-{safe}"
    _atomic_write(path, raw)
    return path


def saved_uploads() -> list[tuple[Path, str]]:
    """(path, original file name) for every saved upload, oldest first."""
    folder = uploads_dir()
    if not folder.exists():
        return []
    files = sorted(p for p in folder.iterdir() if p.is_file() and re.match(r"\d+-", p.name))
    return [(p, p.name.split("-", 1)[1]) for p in files]
