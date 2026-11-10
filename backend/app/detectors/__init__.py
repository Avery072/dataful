"""Run every detector family over a table and return issues sorted by impact.

Detectors are general: they look at column types, roles, names and statistics, never at a
specific dataset. Each one is isolated so a failure in one family can't hide the others.
"""

from __future__ import annotations

import logging
import time

from .. import profile
from .base import Context, Issue, ordered
from .business import contradictions, mixed_units, stale_data, test_records
from .categories import inconsistent_categories
from .duplicates import double_counting, duplicate_records, duplicate_rows, fake_unique_id
from .formats import combined_field, split_id, text_dates, text_numbers, whole_decimals
from .values import constant_column, default_values, disguised_missing, impossible_values, junk_values, missing_values, outliers

log = logging.getLogger("dataful.detectors")

DETECTORS = [
    duplicate_rows, duplicate_records, double_counting, inconsistent_categories,
    disguised_missing, junk_values, default_values, impossible_values, contradictions,
    text_numbers, whole_decimals, text_dates, combined_field, split_id,
    test_records, mixed_units, outliers, missing_values, stale_data, constant_column,
]


def _run(detector, ctx: Context, **kwargs) -> list[Issue]:
    started = time.perf_counter()
    try:
        return detector(ctx, **kwargs)
    except Exception:  # one broken family must not hide the rest
        log.exception("detector %s failed on %s", detector.__name__, ctx.dataset_id)
        return []
    finally:
        log.debug("%s: %s took %.3fs", ctx.dataset_id, detector.__name__, time.perf_counter() - started)


def detect(dataset_id: str, file: str, table: str, rows: int, columns: list[str],
           type_overrides: dict[str, str] | None = None) -> list[Issue]:
    """Issues in one table (the source, or a decision view of it). Ids are stable across views."""
    infos = {c.name: c for c in profile.full_profile(table, columns, type_overrides)}
    ctx = Context(dataset_id=dataset_id, file=file, table=table, rows=rows, columns=columns, info=infos)
    issues: list[Issue] = []
    for detector in DETECTORS:
        issues += _run(detector, ctx)
    # an ID that repeats because of double counting is reported there, not as a fake ID
    counted_keys = {i.columns[0] for i in issues if i.family == "double_counting"}
    issues += _run(fake_unique_id, ctx, skip=counted_keys)
    unique = {i.id: i for i in issues}
    return ordered(list(unique.values()))


__all__ = ["Issue", "detect"]
