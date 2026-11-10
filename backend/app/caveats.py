"""Plain-English warnings shown under a Group-by result, so a number is never quoted without its fine print."""

from __future__ import annotations

from . import issues, store, views
from .detectors.base import MONEY_TOKENS
from .detectors.business import CURRENCIES
from .ops import join_names, singular
from .profile import has_token
from .sql import ident, num

MAX_ISSUE_CAVEATS = 3
AGG_WORDS = {"sum": "totals", "avg": "averages", "count_distinct": "distinct counts", "count": "counts"}


def _rows(n: int) -> str:
    return "1 row" if n == 1 else f"{n:,} rows"


def _are(n: int) -> str:
    return "is" if n == 1 else "are"


def for_group(ds: store.DatasetState, which: str, view: views.BuiltView, result: dict, excluded: dict,
              use_count_unit: bool, where: str) -> list[str]:
    by, agg, measure = result["by"], result["agg"], result["measure"]
    out = []
    if excluded["no_key"]:
        out.append(f"{_rows(excluded['no_key'])} with no {by} {_are(excluded['no_key'])} not counted.")
    if excluded["no_measure"]:
        n = excluded["no_measure"]
        out.append(f"{_rows(n)} with no usable {measure} {_are(n)} left out of the {AGG_WORDS[agg]}.")
    if excluded["no_unit"] and view.count_unit:
        n = excluded["no_unit"]
        out.append(f"{_rows(n)} with no {join_names(view.count_unit['columns'])} {_are(n)} not counted as "
                   f"{view.count_unit['label']}.")
    if agg in ("sum", "avg") and measure:
        out += _mixed_currency(view, by, measure, agg, where)
    if agg == "count" and view.count_unit and not result["count_unit"]:
        label = view.count_unit["label"]
        out.append(f"Counting rows: a shared {singular(label)} is counted once for every row it appears on. "
                   f"Count {label} instead to count each one once.")
    out += _unresolved(ds, which, by, measure, agg, result["count_unit"] and view.count_unit)
    return out


def _currency_columns(view: views.BuiltView) -> list[str]:
    return [c for c in view.columns if has_token(c, {"currency", "ccy", "cur"})]


def _mixed_currency(view: views.BuiltView, by: str, measure: str, agg: str, where: str) -> list[str]:
    """'Amount mixes USD and EUR — totals combine both currencies.' (no conversion is attempted)."""
    if not has_token(measure, MONEY_TOKENS):
        return []
    for col in _currency_columns(view):
        if col == by:
            continue    # each group is a single currency
        found = [v for (v,) in store.query(
            f"SELECT trim({ident(col)}) v FROM {ident(view.table)} WHERE ({where}) AND {num(measure)} IS NOT NULL "
            f"AND {ident(col)} IS NOT NULL GROUP BY 1 ORDER BY count(*) DESC LIMIT 6")]
        if len(found) > 1 and all(v.lower() in CURRENCIES for v in found):
            both = "both" if len(found) == 2 else "all"
            return [f"{measure} mixes {join_names(found)} — {AGG_WORDS[agg]} combine {both} currencies "
                    f"as if they were one."]
    return []


def _unresolved(ds: store.DatasetState, which: str, by: str, measure: str | None, agg: str,
                unit: dict | None) -> list[str]:
    """Undecided issues that change this result: duplicates, and notes on the grouped columns."""
    pool = issues.original(ds) if which == "original" else issues.open_issues(ds)
    out = []
    copies = next((i for i in pool if i.family == "duplicate_rows" and i.kind == "fix"), None)
    if copies:
        out.append(f"{_rows(copies.affected_rows)} {_are(copies.affected_rows)} exact copies of other rows "
                   "and still counted.")
    touched = {by, measure} | set(unit["columns"] if unit else [])
    related = [i for i in pool if i is not copies and any(o["op"] is not None for o in i.options)
               and ((set(i.columns) & touched and len(i.columns) <= 4)
                    or (i.family == "double_counting" and agg == "count" and not unit))]
    out += [f"Not decided yet: {i.title}." for i in related[:MAX_ISSUE_CAVEATS]]
    return out
