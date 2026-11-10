"""Use-case functions behind the HTTP routes: profiles, decisions, rows, review."""

from __future__ import annotations

from . import ai, caveats, issues, ops, orientation, persist, profile, store, views

MAX_ISSUE_COLUMNS = 4


# ---------- datasets & profile ----------

def dataset_json(ds: store.DatasetState) -> dict:
    return ds.to_json() | {"rows_current": views.build_view(ds).rows}


def _column_json(info: profile.ColumnInfo, column_issues: list[issues.Issue]) -> dict:
    trap = any(i.severity == "numbers" for i in column_issues)
    health = "trap" if trap else "gaps" if info.missing_pct > 0.05 else "healthy"
    return {
        "name": info.name, "type": info.type, "role": info.role,
        "missing": info.missing, "missing_pct": round(info.missing_pct, 4), "distinct": info.distinct,
        "top_values": info.top_values, "histogram": info.histogram,
        "min": info.min, "max": info.max, "health": health,
        "issue_ids": [i.id for i in column_issues],
    }


def profile_json(ds: store.DatasetState, which: str) -> dict:
    view = views.get_view(ds, which)
    infos = profile.full_profile(view.table, view.columns, view.type_overrides)
    relevant = issues.original(ds) if which == "original" else issues.open_issues(ds)
    # whole-row issues (exact copies) are shown in the issue list, not on every column header
    column_level = [i for i in relevant if len(i.columns) <= MAX_ISSUE_COLUMNS]
    by_column = {c: [i for i in column_level if c in i.columns] for c in view.columns}
    rules = orientation.build(ds, view.rows, infos, issues.detected(ds))
    return {
        "dataset": dataset_json(ds) | {"rows": view.rows, "columns": len(view.columns)},
        "columns": [_column_json(info, by_column[info.name]) for info in infos],
        "orientation": ds.ai_orientation or rules,
        "ai_reviewed": ds.ai_orientation is not None,
    }


# ---------- decisions ----------
# Every change goes through _commit: rebuild the view (marking decisions that no longer apply
# as broken) and save to disk.

def _commit(ds: store.DatasetState) -> None:
    ds.touch()
    views.build_view(ds)
    persist.save(ds)


def _snapshot(ds: store.DatasetState):
    return list(ds.decisions), [(d, d.enabled, d.broken, d.error) for d in ds.decisions], set(ds.skipped)


def _restore(ds: store.DatasetState, snap) -> None:
    decisions, states, skipped = snap
    ds.decisions = decisions
    for d, enabled, broken, error in states:
        d.enabled, d.broken, d.error = enabled, broken, error
    ds.skipped = skipped
    _commit(ds)


def _plain(op: dict | None, issue: issues.Issue | None, reason: str | None) -> str:
    if op is not None:
        return ops.plain(op)
    return f"Leave as is: {issue.title}" if issue else (reason or "Leave as is")


def add_decision(ds: store.DatasetState, op: dict | None, issue_id: str | None, reason: str | None) -> store.Decision:
    """Add a decision, or replace the one already answering this issue (same place in the chain).

    The op is validated against the columns at its place in the chain, then the new chain is
    built before anything is kept: if it can't be applied, every decision is restored and a
    400 explains why.
    """
    with ds.lock:
        issue = issues.find(ds, issue_id) if issue_id else None
        if issue_id and not issue:
            raise ops.OpError(f"Unknown issue '{issue_id}'")
        if op is None and not issue:
            raise ops.OpError("A 'keep as is' decision (op null) needs an issue_id")
        previous = issues.decision_for(ds, issue_id) if issue_id else None
        position = ds.decisions.index(previous) if previous else len(ds.decisions)
        if op is not None:
            op = ops.validate(op, views.compile_chain(ds, ds.decisions[:position]).columns)
        decision = store.Decision(id=ds.new_decision_id(), op=op, plain=_plain(op, issue, reason),
                                  issue_id=issue_id, reason=reason)
        snap = _snapshot(ds)
        others = [d for d in ds.decisions if not (issue_id and d.issue_id == issue_id)]
        others_before = sum(1 for d in ds.decisions[:position] if d in others)
        ds.decisions = others[:others_before] + [decision] + others[others_before:]
        ds.skipped.discard(issue_id or "")
        _commit(ds)
        if decision.broken:
            error = decision.error
            _restore(ds, snap)
            raise ops.OpError(f"This change can't be applied: {error}")
        return decision


def find_decision(ds: store.DatasetState, decision_id: str) -> store.Decision | None:
    return next((d for d in ds.decisions if d.id == decision_id), None)


def set_enabled(ds: store.DatasetState, decision: store.Decision, enabled: bool) -> store.Decision:
    """Turn a decision on or off. Turning a broken one on retries it (it may be broken again)."""
    with ds.lock:
        if decision.enabled != enabled or decision.broken:
            decision.enabled = enabled
            if enabled:
                decision.broken, decision.error = False, None
            _commit(ds)
        return decision


def remove_decision(ds: store.DatasetState, decision: store.Decision) -> None:
    with ds.lock:
        ds.decisions = [d for d in ds.decisions if d is not decision]
        _commit(ds)


def skip_issue(ds: store.DatasetState, issue: issues.Issue) -> dict:
    with ds.lock:
        ds.skipped.add(issue.id)
        persist.save(ds)
        return issues.to_json(ds, issue)


def reset(ds: store.DatasetState) -> None:
    with ds.lock:
        ds.decisions = []
        ds.skipped = set()
        ds.ai_issues, ds.chat_messages, ds.chat_log = [], [], []
        _commit(ds)


def decisions_file(ds: store.DatasetState) -> dict:
    return {"dataset": ds.id, "file": ds.file, "sheet": ds.sheet, "exported_at": store.now_iso(),
            "decisions": [d.to_json() for d in ds.decisions]}


# ---------- rows ----------

def rows_json(ds: store.DatasetState, which: str, offset: int, limit: int, sort: str | None, direction: str,
              filters_raw: str | None, search: str | None, issue_id: str | None) -> dict:
    view = views.get_view(ds, which)
    filters = views.parse_filters(filters_raw, view.columns)
    extra = None
    if issue_id:
        issue = issues.find(ds, issue_id)
        if not issue:
            raise ops.OpError(f"Unknown issue '{issue_id}'")
        extra = issues.issue_condition(issue, view.columns)
    where = views.row_conditions(view, filters, search, extra)
    limit = max(1, min(limit, views.MAX_LIMIT))
    total, page = views.fetch_rows(view, where, max(0, offset), limit, sort, direction)
    types = view.types()
    kinds = [types.get(c, "text") for c in view.columns]
    return {
        "total": total, "total_unfiltered": view.rows, "columns": view.columns,
        "rows": [[views.typed_value(v, k) for v, k in zip(r[1:], kinds)] for r in page],
        "row_numbers": [r[0] for r in page],
        "flags": issues.page_flags(ds, view.table, view.columns, page, offset, include_resolved=which == "original"),
    }


# ---------- group ----------

def group_json(ds: store.DatasetState, which: str, by: str, measure: str | None, agg: str,
               use_count_unit: bool, filters_raw: str | None) -> dict:
    view = views.get_view(ds, which)
    where = views.row_conditions(view, views.parse_filters(filters_raw, view.columns), None)
    result = views.group(view, by, agg, measure, use_count_unit, where)
    excluded = result.pop("excluded")
    result["caveats"] = caveats.for_group(ds, which, view, result, excluded, use_count_unit, where)
    return result


# ---------- review ----------

def review(ds: store.DatasetState) -> dict:
    ai.review(ds, profile_json(ds, "decisions"))
    return {"orientation": ds.ai_orientation, "issues": issues.all_json(ds)}
