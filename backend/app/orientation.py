"""Rules-based orientation: what one row is, a one-line summary, and column groups.

This is the no-AI baseline; POST /review can replace it with Claude's wording.
"""

from __future__ import annotations

from . import store
from .detectors.base import PERSON_NAME_TOKENS, Issue, entity_noun, noun, plural
from .profile import ColumnInfo, has_token
from .sql import ident

WHO_TOKENS = PERSON_NAME_TOKENS | {"sex", "gender", "age", "email", "mail", "phone", "contact", "owner", "employee",
                                   "athlete", "user", "customer", "reviewer", "author", "staff", "person", "client"}


def _entity(column: str, ds: store.DatasetState) -> str:
    return entity_noun(column, ds.file)


def row_meaning(ds: store.DatasetState, infos: list[ColumnInfo], found: list[Issue]) -> str:
    for issue in found:
        if "keys" in issue.meta:      # shared outcome: one participant in one event
            keys = " × ".join(issue.meta["keys"])
            return f"Each row is one {_entity(issue.meta['entity'], ds)} in one {keys}."
        if "varying" in issue.meta and issue.meta["varying"]:  # a record repeated per child row
            thing = noun(issue.meta["key"])
            return (f"Each row is one {thing} — but some {plural(thing)} repeat once per "
                    f"{issue.meta['varying'][0]}.")
    unique = next((c for c in infos if c.role == "identifier" and c.distinct >= 0.99 * ds.rows
                   and c.nonblank >= 0.99 * ds.rows), None)
    if unique and noun(unique.name) != unique.name:
        how = "is unique" if unique.distinct == ds.rows else "is almost unique"
        return f"Each row is one {noun(unique.name)} ({unique.name} {how})."
    repeating = [c for c in infos if c.role == "identifier" and c.nonblank and c.unique_ratio < 0.99]
    if len(repeating) >= 2:
        return f"Each row is one {_entity(repeating[0].name, ds)} × {_entity(repeating[1].name, ds)} pair."
    if repeating:
        col = repeating[0].name
        return (f"Each row is one entry for a {_entity(col, ds)}; {col} repeats "
                f"(up to {_max_repeat(ds, col):,} rows each).")
    if unique:
        return f"Each row is one record, identified by {unique.name}."
    return f"Each row is one entry in {ds.name}; no single column identifies a row."


def _max_repeat(ds: store.DatasetState, col: str) -> int:
    return store.query(f"SELECT max(c) FROM (SELECT count(*) c FROM {ident(ds.table)} GROUP BY {ident(col)})")[0][0] or 1


def summary(ds: store.DatasetState, view_rows: int, infos: list[ColumnInfo]) -> str:
    parts = [f"{view_rows:,} rows and {len(infos)} columns"]
    span = _time_span(ds, infos)
    if span:
        parts.append(f"spanning {span}")
    gaps = [c.name for c in infos if c.missing_pct > 0.05]
    if gaps:
        parts.append(f"with gaps in {', '.join(gaps[:3])}" + (" and more" if len(gaps) > 3 else ""))
    return ", ".join(parts) + "."


def _time_span(ds: store.DatasetState, infos: list[ColumnInfo]) -> str | None:
    for c in infos:
        if c.role != "time":
            continue
        if c.type == "date" and c.min and c.max:
            return f"{str(c.min)[:4]}–{str(c.max)[:4]}" if str(c.min)[:4] != str(c.max)[:4] else f"{c.min} to {c.max}"
        if c.is_numeric and has_token(c.name, {"year"}) and c.min is not None:
            return f"{int(c.min)}–{int(c.max)}"
    return None


GROUP_ORDER = ["Who", "What", "Where", "When", "Measures", "IDs"]


def _group_of(c: ColumnInfo) -> str:
    if has_token(c.name, WHO_TOKENS) and c.role != "measure" or (has_token(c.name, {"age"}) and c.role == "measure"):
        return "Who"
    if c.role == "geo":
        return "Where"
    if c.role == "time":
        return "When"
    if c.role == "measure":
        return "Measures"
    if c.role == "identifier":
        return "IDs"
    return "What"


def groups(infos: list[ColumnInfo]) -> list[dict]:
    buckets: dict[str, list[str]] = {g: [] for g in GROUP_ORDER}
    for c in infos:
        buckets[_group_of(c)].append(c.name)
    return [{"name": g, "columns": cols} for g, cols in buckets.items() if cols]


def build(ds: store.DatasetState, view_rows: int, infos: list[ColumnInfo], found: list[Issue]) -> dict:
    return {"row_meaning": row_meaning(ds, infos, found), "summary": summary(ds, view_rows, infos),
            "groups": groups(infos), "source": "rules"}

