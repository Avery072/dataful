"""Column profiling: type and role inference, missing counts, top values, histograms. Pure SQL."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field

from . import store
from .sql import MISSING_TOKENS, date_expr, ident, is_blank, lit, not_blank, num, plain_num

N_BINS = 12

ID_TOKENS = {"id", "key", "code", "isbn", "sku", "uuid", "guid", "email", "mail", "phone", "tel", "mobile", "ssn"}
GEO_TOKENS = {"country", "state", "city", "region", "noc", "nation", "zip", "postal", "postcode", "address",
              "location", "province", "county", "continent", "territory", "lat", "lon", "latitude", "longitude"}
TIME_TOKENS = {"date", "time", "timestamp", "year", "month", "day", "week", "quarter", "created", "updated",
               "modified", "epoch"}
BOOL_VALUES = ("true", "false", "yes", "no", "y", "n", "t", "f")


def name_tokens(name: str) -> list[str]:
    """'BookID1' -> ['book', 'id', '1']; 'Department_Region' -> ['department', 'region']."""
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", spaced)
    spaced = re.sub(r"([A-Za-z])(\d)", r"\1 \2", spaced)
    return [t for t in re.split(r"[^a-z0-9]+", spaced.lower()) if t]


def has_token(name: str, tokens: set[str]) -> bool:
    return any(t in tokens for t in name_tokens(name))


@dataclass
class ColumnInfo:
    """Statistics for one column of one table; the input to role inference and every detector."""

    name: str
    rows: int
    nonblank: int
    null: int          # truly empty cells
    distinct: int      # distinct non-blank values
    n_int: int
    n_num: int         # parses as a plain number
    n_num_clean: int   # parses as a number after removing $ , % etc.
    n_bool: int
    date_share: float  # share of a sample of distinct values that parse as dates
    type: str = "text"
    role: str = "text"
    top_values: list[dict] = field(default_factory=list)
    histogram: list[dict] | None = None
    min: str | float | None = None
    max: str | float | None = None

    @property
    def missing(self) -> int:
        return self.rows - self.nonblank

    @property
    def missing_pct(self) -> float:
        return self.missing / self.rows if self.rows else 0.0

    @property
    def unique_ratio(self) -> float:
        return self.distinct / self.nonblank if self.nonblank else 0.0

    @property
    def top_nonblank(self) -> list[tuple[str, int]]:
        """Top values excluding blanks and disguised blanks (requires full_profile)."""
        return [(d["value"], d["count"]) for d in self.top_values
                if str(d["value"]).strip().lower() not in MISSING_TOKENS]

    @property
    def is_numeric(self) -> bool:
        return self.type in ("integer", "decimal")


def _infer_type(c: ColumnInfo) -> str:
    n = c.nonblank
    if n == 0:
        return "text"
    if c.n_bool == n and c.distinct <= 2:
        return "boolean"
    if c.n_int == n:
        return "integer"
    if c.n_num == n:
        return "decimal"
    if c.date_share >= 0.98:
        return "date"
    return "text"


def _infer_role(c: ColumnInfo) -> str:
    if c.type == "boolean":
        return "boolean"
    if c.type == "date" or (c.is_numeric and has_token(c.name, TIME_TOKENS)):
        return "time"
    if has_token(c.name, ID_TOKENS):
        return "identifier"
    if has_token(c.name, GEO_TOKENS):
        return "geo"
    if c.is_numeric:
        return "category" if c.distinct <= 2 else "measure"
    if c.distinct <= 1000 or c.unique_ratio <= 0.05:
        return "category"
    return "text"


def _basic_stats(table: str, columns: list[str]) -> dict[str, dict]:
    """One pass over the table computing counts for every column."""
    aggs = ["count(*)"]
    for col in columns:
        c, nb = ident(col), not_blank(col)
        aggs += [
            f"count(*) FILTER (WHERE {nb})",
            f"count(*) FILTER (WHERE {c} IS NULL)",
            f"count(DISTINCT CASE WHEN {nb} THEN {c} END)",
            f"count(*) FILTER (WHERE {nb} AND regexp_full_match(trim({c}), '[-+]?[0-9]{{1,18}}'))",
            f"count(*) FILTER (WHERE {nb} AND {plain_num(col)} IS NOT NULL)",
            f"count(*) FILTER (WHERE {nb} AND {num(col)} IS NOT NULL)",
            f"count(*) FILTER (WHERE lower(trim({c})) IN {tuple(BOOL_VALUES)!r})",
        ]
    row = store.query(f"SELECT {', '.join(aggs)} FROM {ident(table)}")[0]
    out = {}
    keys = ("nonblank", "null", "distinct", "n_int", "n_num", "n_num_clean", "n_bool")
    for i, col in enumerate(columns):
        vals = row[1 + i * len(keys): 1 + (i + 1) * len(keys)]
        out[col] = dict(zip(keys, vals)) | {"rows": row[0]}
    return out


def _date_share(table: str, col: str) -> float:
    """Share of (up to 2,000) distinct non-numeric values that parse as dates."""
    sql = (f"SELECT count(*) FILTER (WHERE {date_expr(col)} IS NOT NULL), count(*) FROM "
           f"(SELECT DISTINCT {ident(col)} FROM {ident(table)} WHERE {not_blank(col)} LIMIT 2000)")
    hit, total = store.query(sql)[0]
    return hit / total if total else 0.0


_TYPE_CACHE: dict[str, dict[str, ColumnInfo]] = {}
_type_lock = threading.RLock()


def _compute_infos(table: str, columns: list[str]) -> dict[str, ColumnInfo]:
    stats = _basic_stats(table, columns)
    infos = {}
    for col in columns:
        s = stats[col]
        numeric_like = s["nonblank"] and s["n_num"] == s["nonblank"]
        share = 0.0 if numeric_like or not s["nonblank"] else _date_share(table, col)
        infos[col] = ColumnInfo(name=col, date_share=share, **s)
    return infos


def column_infos(table: str, columns: list[str], overrides: dict[str, str] | None = None) -> dict[str, ColumnInfo]:
    """Type + role for every column of a table (cached per table; tables are immutable)."""
    with _type_lock:
        cached = _TYPE_CACHE.setdefault(table, {})
        todo = [c for c in columns if c not in cached]
        if todo:
            cached.update(_compute_infos(table, todo))
        infos = {c: cached[c] for c in columns}
        for info in infos.values():
            info.type = (overrides or {}).get(info.name) or _infer_type(info)
            info.role = _infer_role(info)
    return infos


def forget_table(table: str) -> None:
    _TYPE_CACHE.pop(table, None)


def column_types(table: str, columns: list[str], overrides: dict[str, str] | None = None) -> dict[str, str]:
    return {name: info.type for name, info in column_infos(table, columns, overrides).items()}


# ---------- full column profiles (top values, histograms, ranges) ----------

def _top_values(table: str, col: str) -> list[dict]:
    rows = store.query(f"SELECT {ident(col)}, count(*) AS n FROM {ident(table)} WHERE {ident(col)} IS NOT NULL "
                       f"GROUP BY 1 ORDER BY n DESC, 1 LIMIT 8")
    return [{"value": v, "count": n} for v, n in rows]


def _value_expr(info: ColumnInfo) -> str | None:
    if info.is_numeric:
        return num(info.name)
    if info.type == "date":
        return f"epoch_ms({date_expr(info.name)})"
    return None


def _histogram(table: str, info: ColumnInfo) -> tuple[list[dict] | None, object, object]:
    expr = _value_expr(info)
    if expr is None:
        lo, hi = store.query(f"SELECT min({ident(info.name)}), max({ident(info.name)}) FROM {ident(table)} "
                             f"WHERE {not_blank(info.name)}")[0]
        return None, lo, hi
    lo, hi = store.query(f"SELECT min(v), max(v) FROM (SELECT {expr} AS v FROM {ident(table)}) WHERE v IS NOT NULL")[0]
    if lo is None:
        return None, None, None
    width = (hi - lo) / N_BINS or 1
    rows = store.query(
        f"SELECT least(CAST(floor((v - {lit(float(lo))}) / {lit(float(width))}) AS INTEGER), {N_BINS - 1}) AS b, count(*) "
        f"FROM (SELECT {expr} AS v FROM {ident(table)}) WHERE v IS NOT NULL GROUP BY b ORDER BY b")
    counts = dict(rows)
    bins = [{"start": lo + i * width, "end": lo + (i + 1) * width, "count": counts.get(i, 0)} for i in range(N_BINS)]
    if info.type == "date":
        fmt = store.query(f"SELECT strftime(make_timestamp({int(lo)} * 1000), '%Y-%m-%d'), "
                          f"strftime(make_timestamp({int(hi)} * 1000), '%Y-%m-%d')")[0]
        return bins, fmt[0], fmt[1]
    if info.type == "integer":
        return bins, int(lo), int(hi)
    return bins, lo, hi


def full_profile(table: str, columns: list[str], overrides: dict[str, str] | None = None) -> list[ColumnInfo]:
    """Column infos with top values, histogram and min/max filled in."""
    infos = column_infos(table, columns, overrides)
    out = []
    for col in columns:
        info = infos[col]
        if not info.top_values:
            info.top_values = _top_values(table, col)
            info.histogram, info.min, info.max = _histogram(table, info)
        out.append(info)
    return out


def blank_count(table: str, col: str) -> int:
    return store.query(f"SELECT count(*) FROM {ident(table)} WHERE {is_blank(col)}")[0][0]
