"""Issue state for a dataset: detection on the current view, status from decisions, grid cell flags.

Issues are re-detected on the current view (the source with every enabled decision applied),
cached per distinct decision chain, so every count describes the data the user is looking at.
Issue ids are derived from family + columns (+ key values), so they survive re-detection and
decisions keep pointing at their issue. An issue that a decision resolved no longer shows up
in the current view; it stays listed with the numbers it had in the source, marked resolved.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace

from . import detectors, ops, store, views
from .detectors.base import Issue, ordered
from .ops import FLAG_COLUMN
from .sql import ROW_ID, ident, lit

log = logging.getLogger("dataful.issues")
_RID_TABLE = "issue_rids"
_loaded_rid_sets: set[str] = set()

NOT_SURE = {"label": "Not sure — decide later", "op": None, "skip": True,
            "description": "Leave this open and come back to it later."}


def _detect(ds: store.DatasetState, view: views.BuiltView) -> list[Issue]:
    """Rule-based issues for one (immutable) view table, cached by table name."""
    with ds.lock:
        found = ds.issues_cache.get(view.table)
        if found is None:
            columns = [c for c in view.columns if c != FLAG_COLUMN]   # our own flags are not data problems
            found = detectors.detect(ds.id, ds.file, view.table, view.rows, columns, view.type_overrides)
            ds.issues_cache[view.table] = found
        return found


def original(ds: store.DatasetState) -> list[Issue]:
    """Issues in the untouched source table."""
    return _detect(ds, views.original_view(ds))


def detected(ds: store.DatasetState) -> list[Issue]:
    """Issues in the current view, plus issues resolved by a decision, plus validated AI issues."""
    with ds.lock:
        view = views.build_view(ds)
        current = _detect(ds, view)
        listed = list(current)
        if view.table != ds.table:
            seen = {i.id for i in current}
            decided = {d.issue_id for d in ds.decisions if d.enabled and d.issue_id}
            listed += [i for i in original(ds) if i.id not in seen and i.id in decided]
        listed += ds.ai_issues
        # an AI issue that covers rule issues (one note instead of several) hides the open ones it replaces,
        # unless the user answered it with "keep as is"
        hidden = {rid for ai in ds.ai_issues if status(ds, ai)[0] != "kept"
                  for rid in ai.meta.get("replaces", [])}
        listed = [i for i in listed if i.id not in hidden or status(ds, i)[0] not in ("open", "skipped")]
        return ordered([_present(i, view.columns) for i in listed])


def _present(issue: Issue, columns: list[str]) -> Issue:
    """Only options that fit the current view, no repeats, and one 'Not sure' per question."""
    options, seen = [], set()
    for opt in issue.options:
        if opt.get("skip"):
            continue
        if opt["op"] is not None:
            try:
                ops.validate(opt["op"], columns)
            except ops.OpError:
                continue
        key = json.dumps(opt["op"], sort_keys=True)
        if key not in seen:
            seen.add(key)
            options.append(opt)
    if issue.kind == "question" and issue.question:
        options.append(dict(NOT_SURE))
    return replace(issue, options=options)


def find(ds: store.DatasetState, issue_id: str) -> Issue | None:
    found = next((i for i in detected(ds) if i.id == issue_id), None)
    return found or next((i for i in original(ds) if i.id == issue_id), None)


def decision_for(ds: store.DatasetState, issue_id: str) -> store.Decision | None:
    """The decision that answers an issue (latest wins if an old file holds several)."""
    return next((d for d in reversed(ds.decisions) if d.issue_id == issue_id), None)


def status(ds: store.DatasetState, issue: Issue) -> tuple[str, str | None]:
    """(status, decision_id): the latest enabled decision for the issue wins."""
    for d in reversed(ds.decisions):
        if d.issue_id == issue.id and d.enabled:
            kind = (d.op or {}).get("op")
            if d.op is None or kind == "keep_separate":
                return "kept", d.id
            if kind in ("flag_rows", "flag_duplicates"):
                return "flagged", d.id
            return "resolved", d.id
    if issue.id in ds.skipped:
        return "skipped", None
    return "open", None


def to_json(ds: store.DatasetState, issue: Issue) -> dict:
    state, decision_id = status(ds, issue)
    out = issue.to_json(state, decision_id)
    override = ds.ai_issue_text.get(issue.id)
    if override:
        for key in ("title", "detail", "question"):
            if override.get(key):
                out[key] = override[key]
        labels = override.get("option_labels") or []
        for opt, label in zip([o for o in out["options"] if not o.get("skip")], labels):
            if label:
                opt["label"] = label
        out["source"] = "ai"
    return out


def all_json(ds: store.DatasetState) -> list[dict]:
    return [to_json(ds, i) for i in detected(ds)]


def open_issues(ds: store.DatasetState) -> list[Issue]:
    return [i for i in detected(ds) if status(ds, i)[0] in ("open", "skipped")]


# ---------- grid flags ----------

def _ensure_rid_set(issue: Issue) -> str:
    """Store an issue's row ids in DuckDB once, so filtering by issue is a semi-join."""
    key = f"{issue.id}#{id(issue)}"
    if key not in _loaded_rid_sets:
        store.execute(f"CREATE TABLE IF NOT EXISTS {_RID_TABLE} (issue_key VARCHAR, rid BIGINT)")
        store.execute(f"INSERT INTO {_RID_TABLE} SELECT ?, unnest(?::BIGINT[])", [key, sorted(issue.flag_rids or [])])
        _loaded_rid_sets.add(key)
    return key


def issue_condition(issue: Issue, columns: list[str]) -> str:
    """SQL condition selecting the rows an issue is about (for 'click an issue to filter the grid')."""
    if issue.flag_rids is not None:
        key = _ensure_rid_set(issue)
        return f"{ROW_ID} IN (SELECT rid FROM {_RID_TABLE} WHERE issue_key = {lit(key)})"
    if issue.flag_expr and all(c in columns for c in issue.columns):
        return f"({issue.flag_expr})"
    return "TRUE" if all(c in columns for c in issue.columns) else "FALSE"


def page_flags(ds: store.DatasetState, view_table: str, columns: list[str], page: list[tuple], offset: int,
               include_resolved: bool = False) -> dict:
    """{row offset: {column: issue id}} for cells on this page affected by open issues.

    Offsets are absolute positions in the filtered/sorted result (offset + index on the page).
    """
    if not page:
        return {}
    rids = [r[0] for r in page]
    position = {rid: offset + i for i, rid in enumerate(rids)}
    flags: dict[int, dict[str, str]] = {}

    def mark(rid: int, column: str, iid: str) -> None:
        flags.setdefault(position[rid], {}).setdefault(column, iid)

    pool = original(ds) if include_resolved else open_issues(ds)
    candidates = [i for i in pool if i.flag_column in columns]
    exprs = [i for i in candidates if i.flag_rids is None and i.flag_expr and all(c in columns for c in i.columns)]
    for issue in candidates:
        if issue.flag_rids is not None:
            for rid in rids:
                if rid in issue.flag_rids:
                    mark(rid, issue.flag_column, issue.id)
    if exprs:
        selects = ", ".join(f"coalesce(({i.flag_expr}), FALSE)" for i in exprs)
        try:
            rows = store.query(f"SELECT {ROW_ID}, {selects} FROM {ident(view_table)} "
                               f"WHERE {ROW_ID} IN (SELECT unnest(?::BIGINT[]))", [rids])
        except Exception:  # a highlight must never break the grid
            log.exception("flag query failed for %s", ds.id)
            rows = []
        for rid, *hits in rows:
            for issue, hit in zip(exprs, hits):
                if hit:
                    mark(rid, issue.flag_column, issue.id)
    return {str(k): v for k, v in sorted(flags.items())}


def warm(ds: store.DatasetState) -> None:
    detected(ds)
