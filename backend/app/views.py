"""Decision views over the read-only source, plus the grid queries (rows, group, preview, export).

The current view is the source table with every enabled decision applied in order:
view_n = op_n(view_{n-1}). A decision that no longer fits (unknown column, SQL that fails) is
marked broken and disabled instead of breaking the dataset.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field

import duckdb

from . import ops, persist, profile, store
from .sql import MISSING_TOKENS, ROW_ID, date_expr, ident, is_blank, lit, not_blank, num

MAX_LIMIT = 500
KEEP_VIEWS = 4                      # materialized views kept per dataset (older ones are dropped)
MAX_SAFE_INTEGER = 2 ** 53          # larger integers are returned as text so JavaScript keeps every digit


@dataclass
class BuiltView:
    """The materialized result of applying the enabled decisions, in order."""

    table: str
    columns: list[str]
    rows: int
    type_overrides: dict[str, str] = field(default_factory=dict)
    count_unit: dict | None = None

    def types(self) -> dict[str, str]:
        return profile.column_types(self.table, self.columns, self.type_overrides)


def original_view(ds: store.DatasetState) -> BuiltView:
    return BuiltView(table=ds.table, columns=list(ds.columns), rows=ds.rows)


# ---------- the decision chain ----------

@dataclass
class Chain:
    """Enabled decisions compiled into one nested SELECT (not yet materialized)."""

    src: str
    columns: list[str]
    overrides: dict[str, str]
    count_unit: dict | None
    steps: list[tuple[store.Decision, str]]                 # (decision, SQL source after it)
    failures: list[tuple[store.Decision, str]]              # (decision, why it could not apply)


def chain_signature(decisions: list[store.Decision]) -> str:
    """Identical enabled chains give identical views, so caches are keyed by this."""
    return json.dumps([d.op for d in decisions if d.enabled and d.op is not None], sort_keys=True)


def _error_text(exc: Exception) -> str:
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    return text[:300]


def _apply_op(op: dict, src: str, columns: list[str], types: dict[str, str], step: int) -> ops.Compiled:
    """Validate and compile one op over `src`, and ask DuckDB to bind it (catches type/SQL errors early)."""
    clean = ops.validate(op, columns)
    compiled = ops.compile_op(clean, src, columns, types)
    compiled.sql = f"({compiled.sql}) AS step{step}"
    store.query(f"SELECT * FROM {compiled.sql} LIMIT 0")
    return compiled


def compile_chain(ds: store.DatasetState, decisions: list[store.Decision]) -> Chain:
    base_types = profile.column_types(ds.table, ds.columns)
    chain = Chain(src=ident(ds.table), columns=list(ds.columns), overrides={}, count_unit=None, steps=[], failures=[])
    for i, decision in enumerate(decisions):
        if not decision.enabled or decision.op is None:
            continue
        types = {c: chain.overrides.get(c) or base_types.get(c, "text") for c in chain.columns}
        try:
            compiled = _apply_op(decision.op, chain.src, chain.columns, types, i)
        except (ops.OpError, duckdb.Error) as exc:
            chain.failures.append((decision, _error_text(exc)))
            continue
        chain.src, chain.columns = compiled.sql, compiled.columns
        chain.overrides.update(compiled.type_overrides)
        chain.count_unit = compiled.count_unit or chain.count_unit
        chain.steps.append((decision, chain.src))
    return chain


def chain_types(ds: store.DatasetState, chain: Chain) -> dict[str, str]:
    base_types = profile.column_types(ds.table, ds.columns)
    return {c: chain.overrides.get(c) or base_types.get(c, "text") for c in chain.columns}


def _runtime_failure(chain: Chain) -> tuple[store.Decision, str] | None:
    """The first step whose SQL fails when actually run (rare: binding already succeeded)."""
    for decision, src in chain.steps:
        try:
            store.query(f"SELECT count(*) FROM {src}")
        except duckdb.Error as exc:
            return decision, _error_text(exc)
    return None


def _table_name(ds: store.DatasetState, signature: str) -> str:
    return f"view_{ds.table}_{hashlib.sha1(signature.encode()).hexdigest()[:10]}"


def build_view(ds: store.DatasetState) -> BuiltView:
    """The 'with my decisions' view, materialized once per distinct decision chain.

    Decisions that cannot be applied are marked broken (and disabled) and the view is built
    without them, so a dataset always loads.
    """
    with ds.lock:
        while True:
            signature = chain_signature(ds.decisions)
            if signature in ds.view_cache:
                return ds.view_cache[signature]
            chain = compile_chain(ds, ds.decisions)
            failure = chain.failures[0] if chain.failures else None
            if not failure and chain.steps:
                table = _table_name(ds, signature)
                try:
                    store.execute(f"CREATE OR REPLACE TABLE {ident(table)} AS SELECT * FROM {chain.src} ORDER BY {ROW_ID}")
                except duckdb.Error as exc:
                    failure = _runtime_failure(chain) or (chain.steps[-1][0], _error_text(exc))
            if failure:
                for decision, error in chain.failures or [failure]:
                    decision.mark_broken(error)
                persist.save(ds)
                continue          # rebuild without the broken decisions
            if not chain.steps:
                view = original_view(ds)
            else:
                rows = store.query(f"SELECT count(*) FROM {ident(table)}")[0][0]
                view = BuiltView(table, chain.columns, rows, chain.overrides, chain.count_unit)
            _remember(ds, signature, view)
            return view


def _remember(ds: store.DatasetState, signature: str, view: BuiltView) -> None:
    ds.view_cache[signature] = view
    while len(ds.view_cache) > KEEP_VIEWS:
        old = ds.view_cache.pop(next(iter(ds.view_cache)))
        if old.table != ds.table and old.table != view.table:
            ds.issues_cache.pop(old.table, None)
            store.execute(f"DROP TABLE IF EXISTS {ident(old.table)}")
            profile.forget_table(old.table)


def get_view(ds: store.DatasetState, which: str) -> BuiltView:
    return original_view(ds) if which == "original" else build_view(ds)


# ---------- rows ----------

def parse_filters(raw: str | None, columns: list[str]) -> list[dict]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ops.OpError(f"filters is not valid JSON: {exc}") from exc
    return ops.validate_filters(data, columns)


def _sort_expr(col: str, kind: str) -> str:
    if kind in ("integer", "decimal"):
        return num(col)
    if kind == "date":
        return date_expr(col)
    return ident(col)


def row_conditions(view: BuiltView, filters: list[dict], search: str | None, extra: str | None = None) -> str:
    parts = [ops.where_sql(filters, view.types())] if filters else []
    if search:
        hay = "concat_ws(' ', " + ", ".join(ident(c) for c in view.columns) + ")"
        parts.append(f"{hay} ILIKE {lit('%' + search + '%')}")
    if extra:
        parts.append(extra)
    return " AND ".join(parts) or "TRUE"


def fetch_rows(view: BuiltView, where: str, offset: int, limit: int, sort: str | None, direction: str):
    """Total count and one page of rows (row ids first) for the current view."""
    total = store.query(f"SELECT count(*) FROM {ident(view.table)} WHERE {where}")[0][0]
    order = ROW_ID
    if sort in view.columns:
        d = "DESC" if direction == "desc" else "ASC"
        order = f"{_sort_expr(sort, view.types().get(sort, 'text'))} {d} NULLS LAST, {ROW_ID}"
    cols = ", ".join([ROW_ID] + [ident(c) for c in view.columns])
    rows = store.query(f"SELECT {cols} FROM {ident(view.table)} WHERE {where} ORDER BY {order} "
                       f"LIMIT {int(limit)} OFFSET {int(offset)}")
    return total, rows


_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_TRUE = {"true", "yes", "y", "t", "1"}


def typed_value(value: str | None, kind: str):
    """A cell as JSON: numbers as numbers, booleans as booleans, empty as null.

    Values that don't fit the column type (an unmarked 'NA', '4/2/2021' in a date column) stay
    as their original text so the user still sees the messy cell.
    """
    if value is None or not value.strip():
        return None
    text = value.strip()
    if kind == "integer" and not (len(text) > 1 and text.lstrip("+-").startswith("0")):
        try:
            number = int(text)
            return number if abs(number) < MAX_SAFE_INTEGER else value
        except ValueError:
            return value
    if kind == "decimal":
        try:
            number = float(text)
        except ValueError:
            return value
        if not math.isfinite(number):
            return value
        return int(number) if number.is_integer() and abs(number) < MAX_SAFE_INTEGER else number
    if kind == "boolean" and text.lower() not in MISSING_TOKENS:
        return text.lower() in _TRUE
    if kind == "date" and _ISO_DATE.match(text):
        return text[:10] if text[10:].strip() in ("", "00:00:00") else text.replace(" ", "T")
    return value


# ---------- group ----------

def unit_key(columns: list[str], alias: str = "") -> str:
    return "concat_ws(chr(31), " + ", ".join(f"coalesce({alias}{ident(c)}, '')" for c in columns) + ")"


def group(view: BuiltView, by: str, agg: str, measure: str | None, use_count_unit: bool, where: str) -> dict:
    """Pivot-style counts/sums by one column. With a count unit, each unit is counted once per group.

    Rows with no group key (or no usable measure / count unit) are left out and counted in
    `excluded`, so the caller can say so in plain English.
    """
    if by not in view.columns:
        raise ops.OpError(f"Unknown column '{by}'")
    if agg in ("sum", "avg", "count_distinct") and measure not in view.columns:
        raise ops.OpError(f"agg '{agg}' needs a valid measure column")
    unit = view.count_unit if use_count_unit and view.count_unit else None
    if unit and not all(c in view.columns for c in unit["columns"]):
        unit = None
    t = ident(view.table)
    key_ok = not_blank(by)
    measure_ok = "TRUE"
    if agg in ("sum", "avg"):
        measure_ok = f"({num(measure)} IS NOT NULL)"
    elif agg == "count_distinct":
        measure_ok = not_blank(measure)
    unit_ok = "(" + " AND ".join(not_blank(c) for c in unit["columns"]) + ")" if unit else "TRUE"
    no_key, no_measure, no_unit = store.query(
        f"SELECT count(*) FILTER (WHERE NOT {key_ok}), count(*) FILTER (WHERE {key_ok} AND NOT {measure_ok}), "
        f"count(*) FILTER (WHERE {key_ok} AND {measure_ok} AND NOT {unit_ok}) FROM {t} WHERE {where}")[0]
    kept = f"({where}) AND {key_ok} AND {measure_ok} AND {unit_ok}"
    key = ident(by)
    if agg == "count_distinct":
        sql = f"SELECT {key} AS k, count(DISTINCT {ident(measure)}) AS v, count(*) AS n FROM {t} WHERE {kept} GROUP BY k"
    elif unit:
        # collapse to one row per (group, unit) first, then aggregate
        m = num(measure) if measure and agg != "count" else "NULL"
        inner = (f"SELECT {key} AS k, {unit_key(unit['columns'])} AS u, any_value({m}) AS m, count(*) AS rn "
                 f"FROM {t} WHERE {kept} GROUP BY k, u")
        value = {"count": "count(*)", "sum": "sum(m)", "avg": "avg(m)"}[agg]
        sql = f"SELECT k, {value} AS v, sum(rn) AS n FROM ({inner}) GROUP BY k"
    else:
        value = "count(*)" if agg == "count" else f"{agg}({num(measure)})"
        sql = f"SELECT {key} AS k, {value} AS v, count(*) AS n FROM {t} WHERE {kept} GROUP BY k"
    rows = store.query(f"{sql} ORDER BY v DESC NULLS LAST, k LIMIT 50")
    return {
        "by": by, "agg": agg, "measure": measure,
        "count_unit": unit["label"] if unit else None,
        "groups": [{"key": k, "value": _clean_number(v), "rows": int(n)} for k, v, n in rows],
        "excluded_rows": no_key + no_measure + no_unit,
        "excluded": {"no_key": no_key, "no_measure": no_measure, "no_unit": no_unit},
    }


def _clean_number(v):
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return round(v, 4) if isinstance(v, float) else v


# ---------- preview ----------

@dataclass
class _Base:
    """The view a preview starts from: a SQL source, its columns and types."""

    src: str
    columns: list[str]
    types: dict[str, str]
    rows: int


def _preview_base(ds: store.DatasetState, replacing: store.Decision | None) -> _Base:
    current = build_view(ds)
    if replacing is None or not replacing.enabled or replacing.op is None:
        return _Base(ident(current.table), current.columns, current.types(), current.rows)
    # re-answering a question: preview against the chain without the decision being replaced
    chain = compile_chain(ds, [d for d in ds.decisions if d is not replacing])
    src = f"(SELECT * FROM {chain.src})"
    rows = store.query(f"SELECT count(*) FROM {src}")[0][0]
    return _Base(src, chain.columns, chain_types(ds, chain), rows)


def preview(ds: store.DatasetState, op: dict, replacing: store.Decision | None = None) -> dict:
    """What would change if `op` were added on top of the current decisions."""
    with ds.lock:
        base = _preview_base(ds, replacing)
    clean = ops.validate(op, base.columns)
    compiled = ops.compile_op(clean, base.src, base.columns, base.types)
    new_src = f"({compiled.sql})"
    after_n = store.query(f"SELECT count(*) FROM {new_src}")[0][0]
    changes, changed_rows = _diff(base, compiled, new_src, clean)
    removed = base.rows - after_n
    impact = _impact(clean, base, removed, changed_rows)
    return {"affected_rows": changed_rows + removed, "impact": impact, "changes": changes,
            "rows_before": base.rows, "rows_after": after_n}


def _diff(base: _Base, compiled: ops.Compiled, new_src: str, op: dict) -> tuple[list[dict], int]:
    """Cell-level before/after pairs (top 20 by count) and the number of rows with any change."""
    old_cols = set(base.columns)
    # new columns from a split/combine show the source value as "before"; others start blank
    source_cols = [c for c in ops.op_columns(op) if c in old_cols]
    before_expr = "NULL"
    if op["op"] in ("split_column", "combine_columns") and source_cols:
        before_expr = "concat_ws(' + ', " + ", ".join(f"o.{ident(c)}" for c in source_cols) + ")"
    pairs = []
    for col in compiled.columns:
        if col in old_cols:
            pairs.append((col, f"o.{ident(col)}", f"n.{ident(col)}"))
        else:
            pairs.append((col, before_expr, f"n.{ident(col)}"))
    join = f"FROM {base.src} o JOIN {new_src} n USING ({ROW_ID})"
    changed_any = " OR ".join(f"({b}) IS DISTINCT FROM ({a})" for _, b, a in pairs) or "FALSE"
    changed_rows = store.query(f"SELECT count(*) {join} WHERE {changed_any}")[0][0]
    if not changed_rows:
        return [], 0
    unions = " UNION ALL ".join(
        f"SELECT {lit(col)} AS col, CAST({b} AS VARCHAR) AS b, CAST({a} AS VARCHAR) AS a, count(*) AS n "
        f"{join} WHERE ({b}) IS DISTINCT FROM ({a}) GROUP BY 2, 3"
        for col, b, a in pairs)
    rows = store.query(f"SELECT * FROM ({unions}) ORDER BY n DESC LIMIT 20")
    return [{"column": c, "before": b, "after": a, "count": n} for c, b, a, n in rows], changed_rows


def _impact(op: dict, base: _Base, removed: int, changed: int) -> str:
    k = op["op"]
    total = base.rows
    if k == "set_count_unit":
        filled = " AND ".join(f"NOT {is_blank(c)}" for c in op["columns"])
        rows, units = store.query(f"SELECT count(*), count(DISTINCT {unit_key(op['columns'])}) "
                                  f"FROM {base.src} WHERE {filled}")[0]
        return (f"Counts will treat rows that share one {ops.singular(op['label'])} as one: "
                f"{rows:,} rows represent {units:,} {op['label']}. No values change.")
    if k == "keep_separate":
        return "No data changes; Dataful will remember these are different and stop asking."
    if removed:
        return f"Removes {removed:,} {'row' if removed == 1 else 'rows'} ({total:,} → {total - removed:,})."
    if changed:
        return f"Changes {changed:,} of {total:,} rows."
    return "No rows would change."


# ---------- export ----------

def export_csv(view: BuiltView, path) -> None:
    cols = ", ".join(ident(c) for c in view.columns)
    store.execute(f"COPY (SELECT {cols} FROM {ident(view.table)} ORDER BY {ROW_ID}) TO {lit(str(path))} "
                  f"(HEADER, DELIMITER ',')")
