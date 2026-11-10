"""The fixed operation vocabulary: validation, plain-English text, and op -> SQL compilation.

Every op is a pure SELECT over the previous view, so the source table is never modified:
view_n = op_n(view_{n-1}).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .sql import ROW_ID, date_expr, ident, is_blank, lit, lit_list, num

FLAG_COLUMN = "Flag"
FILTER_OPS = {"=", "!=", "<", ">", "is_missing", "not_missing", "contains", "in"}
TYPES = {"text", "integer", "decimal", "date"}
MAX_RECODE = 500


class OpError(ValueError):
    """An op that is not part of the vocabulary or does not fit the current table."""


# ---------- validation ----------

def _str(op: dict, key: str) -> str:
    value = op.get(key)
    if not isinstance(value, str) or not value:
        raise OpError(f"'{key}' must be a non-empty string")
    return value


def _str_list(op: dict, key: str, min_len: int = 1) -> list[str]:
    value = op.get(key)
    if not isinstance(value, list) or len(value) < min_len or not all(isinstance(v, str) for v in value):
        raise OpError(f"'{key}' must be a list of at least {min_len} string(s)")
    return value


def _column(op: dict, key: str, columns: list[str]) -> str:
    name = _str(op, key)
    if name not in columns:
        raise OpError(f"Unknown column '{name}'")
    return name


def _columns(op: dict, key: str, columns: list[str], min_len: int = 1) -> list[str]:
    names = _str_list(op, key, min_len)
    missing = [n for n in names if n not in columns]
    if missing:
        raise OpError(f"Unknown column(s): {', '.join(missing)}")
    return names


def validate_filters(filters: Any, columns: list[str]) -> list[dict]:
    if not isinstance(filters, list):
        raise OpError("'where' / filters must be a list")
    clean = []
    for f in filters:
        if not isinstance(f, dict) or f.get("op") not in FILTER_OPS:
            raise OpError(f"Bad filter: {f!r}")
        if f.get("column") not in columns:
            raise OpError(f"Unknown filter column '{f.get('column')}'")
        if f["op"] == "in" and not isinstance(f.get("value"), list):
            raise OpError("'in' filter needs a list value")
        other = f.get("other_column")
        if other is not None:
            if f["op"] not in ("=", "!=", "<", ">"):
                raise OpError("'other_column' works with =, !=, < and >")
            if other not in columns:
                raise OpError(f"Unknown filter column '{other}'")
            clean.append({"column": f["column"], "op": f["op"], "other_column": other})
            continue
        clean.append({"column": f["column"], "op": f["op"], "value": f.get("value")})
    return clean


def validate(op: Any, columns: list[str]) -> dict:
    """Check an op against the vocabulary and the current columns; return a clean copy."""
    if not isinstance(op, dict):
        raise OpError("op must be an object")
    kind = op.get("op")
    c = columns
    if kind == "mark_missing":
        return {"op": kind, "column": _column(op, "column", c), "values": _str_list(op, "values")}
    if kind == "fill_blank":
        value = op.get("value")
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            raise OpError("'value' must be a string or number")
        return {"op": kind, "column": _column(op, "column", c), "value": value}
    if kind == "change_type":
        if op.get("to") not in TYPES:
            raise OpError(f"'to' must be one of {sorted(TYPES)}")
        return {"op": kind, "column": _column(op, "column", c), "to": op["to"]}
    if kind == "split_column":
        into = _str_list(op, "into", 2)[:2]
        return {"op": kind, "column": _column(op, "column", c), "sep": _str(op, "sep"), "into": into}
    if kind == "merge_values":
        return {"op": kind, "column": _column(op, "column", c), "from": _str_list(op, "from"), "to": _str(op, "to")}
    if kind == "recode_values":
        mapping = op.get("mapping")
        if not isinstance(mapping, dict) or not all(isinstance(k, str) and isinstance(v, str) and v
                                                    for k, v in mapping.items()):
            raise OpError("'mapping' must be an object of {old value: new value} strings")
        mapping = {k: v for k, v in mapping.items() if k != v}
        if not mapping or len(mapping) > MAX_RECODE:
            raise OpError(f"'mapping' must change between 1 and {MAX_RECODE} values")
        return {"op": kind, "column": _column(op, "column", c), "mapping": mapping}
    if kind == "combine_columns":
        sep = op.get("sep", "")
        if not isinstance(sep, str):
            raise OpError("'sep' must be a string")
        return {"op": kind, "columns": _columns(op, "columns", c, 2), "sep": sep, "into": _str(op, "into")}
    if kind == "set_count_unit":
        return {"op": kind, "columns": _columns(op, "columns", c), "label": _str(op, "label")}
    if kind == "drop_rows":
        return {"op": kind, "where": validate_filters(op.get("where"), c)}
    if kind == "flag_rows":
        return {"op": kind, "where": validate_filters(op.get("where"), c), "label": _str(op, "label")}
    if kind == "remove_duplicates":
        cols = op.get("columns")
        return {"op": kind, "columns": None if cols is None else _columns(op, "columns", c)}
    if kind == "merge_records":
        if op.get("keep") not in ("first", "last"):
            raise OpError("'keep' must be 'first' or 'last'")
        return {"op": kind, "key": _columns(op, "key", c), "keep": op["keep"]}
    if kind == "keep_separate":
        return {"op": kind, "column": _column(op, "column", c), "values": _str_list(op, "values")}
    if kind == "flag_duplicates":
        return {"op": kind, "key": _columns(op, "key", c), "label": _str(op, "label")}
    raise OpError(f"Unknown op '{kind}'")


# ---------- plain English ----------

def singular(word: str) -> str:
    """'medals' -> 'medal', 'deals' -> 'deal', 'categories' -> 'category' (labels are short nouns)."""
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def join_names(names: list[str]) -> str:
    """['A'] -> 'A'; ['A', 'B', 'C'] -> 'A, B and C'."""
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _q(values: list[str], limit: int = 3) -> str:
    shown = ", ".join(f"'{v}'" for v in values[:limit])
    return shown + (f" and {len(values) - limit} more" if len(values) > limit else "")


def describe_filters(filters: list[dict]) -> str:
    words = {"=": "is", "!=": "is not", "<": "is below", ">": "is above", "contains": "contains", "in": "is one of"}
    parts = []
    for f in filters:
        if f.get("other_column"):
            parts.append(f"{f['column']} {words[f['op']]} {f['other_column']}")
        elif f["op"] == "is_missing":
            parts.append(f"{f['column']} is blank")
        elif f["op"] == "not_missing":
            parts.append(f"{f['column']} is filled in")
        elif f["op"] == "in":
            parts.append(f"{f['column']} is {_q([str(v) for v in f['value']])}")
        else:
            parts.append(f"{f['column']} {words[f['op']]} '{f.get('value')}'")
    return " and ".join(parts) or "every row"


def plain(op: dict) -> str:
    """One readable sentence for the decision list."""
    k = op["op"]
    if k == "mark_missing":
        return f"Treat {_q(op['values'])} in {op['column']} as missing"
    if k == "fill_blank":
        return f"Blank {op['column']} means {op['value']!s}"
    if k == "change_type":
        return f"Treat {op['column']} as {op['to']}"
    if k == "split_column":
        return f"Split {op['column']} on '{op['sep']}' into {op['into'][0]} and {op['into'][1]}"
    if k == "merge_values":
        verb = "means" if len(op["from"]) == 1 else "mean"
        return f"In {op['column']}, {_q(op['from'])} {verb} '{op['to']}'"
    if k == "combine_columns":
        return f"Combine {join_names(op['columns'])} into {op['into']}"
    if k == "set_count_unit":
        return f"Count each {singular(op['label'])} once, even when several rows share it"
    if k == "drop_rows":
        return f"Exclude rows where {describe_filters(op['where'])}"
    if k == "flag_rows":
        return f"Flag rows where {describe_filters(op['where'])} as '{op['label']}'"
    if k == "remove_duplicates":
        scope = "identical rows" if op["columns"] is None else f"rows with the same {join_names(op['columns'])}"
        return f"Keep one copy of {scope}"
    if k == "merge_records":
        return f"Rows with the same {join_names(op['key'])} are one record (keep the {op['keep']})"
    if k == "recode_values":
        targets = sorted(set(op["mapping"].values()))
        n = len(op["mapping"])
        return f"In {op['column']}, rewrite {n} spelling{'s' if n != 1 else ''} as {_q(targets, 4)}"
    if k == "keep_separate":
        verb = "is a separate value" if len(op["values"]) == 1 else "are different things"
        return f"{_q(op['values'])} in {op['column']} {verb}"
    if k == "flag_duplicates":
        return f"Mark rows that share {join_names(op['key'])} as '{op['label']}'"
    return k


# ---------- SQL compilation ----------

def filter_sql(f: dict, col_types: dict[str, str] | None = None) -> str:
    """One filter as a SQL boolean. Comparisons are numeric/date-aware when the column type is known."""
    col, op, value = f["column"], f["op"], f.get("value")
    c = ident(col)
    kind = (col_types or {}).get(col, "text")
    if f.get("other_column"):
        return _compare_columns(col, op, f["other_column"], kind, (col_types or {}).get(f["other_column"], "text"))
    if op == "is_missing":
        return is_blank(col)
    if op == "not_missing":
        return f"(NOT {is_blank(col)})"
    if op == "contains":
        return f"({c} ILIKE {lit('%' + str(value) + '%')})"
    if op == "in":
        return f"({c} IN {lit_list(str(v) for v in value)})"
    if op in ("<", ">"):
        return _compare_sql(col, op, value, kind)
    if op == "!=":
        return f"({c} IS DISTINCT FROM {lit(str(value))})"
    return f"({c} = {lit(str(value))})"


def _compare_sql(col: str, op: str, value: Any, kind: str) -> str:
    """'<' / '>' compare as numbers or dates when the value (or column) is one, else as text."""
    text = str(value)
    if kind in ("integer", "decimal") or _is_number(text):
        return f"({num(col)} {op} TRY_CAST({lit(text)} AS DOUBLE))"
    if kind == "date" or _is_date(text):
        return f"({date_expr(col)} {op} TRY_CAST({lit(text)} AS TIMESTAMP))"
    return f"({ident(col)} {op} {lit(text)})"


def _compare_columns(a: str, op: str, b: str, kind_a: str, kind_b: str) -> str:
    """Row-wise comparison of two columns: as dates, numbers, or text. Blank on either side never matches."""
    sql_op = {"=": "=", "!=": "<>", "<": "<", ">": ">"}[op]
    kinds = {kind_a, kind_b}
    if kinds <= {"date"} or (kinds & {"date"} and not kinds & {"integer", "decimal"}):
        x, y = date_expr(a), date_expr(b)
    elif kinds <= {"integer", "decimal"}:
        x, y = num(a), num(b)
    else:
        x, y = ident(a), ident(b)
    return f"(({x}) {sql_op} ({y}))"


def _is_number(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def _is_date(text: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", text))


def where_sql(filters: list[dict], col_types: dict[str, str] | None = None) -> str:
    return " AND ".join(filter_sql(f, col_types) for f in filters) or "TRUE"


def _number_text(expr: str, integer: bool) -> str:
    """Render a DOUBLE expression back to tidy text ('53' rather than '53.0')."""
    if integer:
        return f"CAST(CAST(round({expr}) AS BIGINT) AS VARCHAR)"
    return (f"CASE WHEN {expr} = floor({expr}) AND abs({expr}) < 1e15 "
            f"THEN CAST(CAST({expr} AS BIGINT) AS VARCHAR) ELSE CAST({expr} AS VARCHAR) END")


def _change_type_expr(col: str, to: str) -> str:
    c = ident(col)
    if to == "text":
        return c
    if to in ("integer", "decimal"):
        return _number_text(num(col), integer=(to == "integer"))
    # date: also understands unix epoch seconds
    epoch = f"CASE WHEN regexp_full_match(trim({c}), '\\d{{9,10}}') THEN to_timestamp(CAST(trim({c}) AS BIGINT))::TIMESTAMP END"
    return f"strftime(COALESCE({date_expr(col)}, {epoch}), '%Y-%m-%d')"


def _select(columns: list[str], replace: dict[str, str] | None = None, extra: list[str] | None = None) -> str:
    replace = replace or {}
    parts = [ROW_ID] + [f"{replace[c]} AS {ident(c)}" if c in replace else ident(c) for c in columns]
    return ", ".join(parts + (extra or []))


def _with_flag(columns: list[str], cond: str, label: str) -> tuple[list[str], str]:
    """Add (or extend) the visible Flag column for rows matching cond."""
    new = f"CASE WHEN {cond} THEN {lit(label)} END"
    if FLAG_COLUMN in columns:
        expr = f"CASE WHEN {cond} THEN concat_ws('; ', {ident(FLAG_COLUMN)}, {lit(label)}) ELSE {ident(FLAG_COLUMN)} END"
        return columns, _select(columns, {FLAG_COLUMN: expr})
    return columns + [FLAG_COLUMN], _select(columns, extra=[f"{new} AS {ident(FLAG_COLUMN)}"])


@dataclass
class Compiled:
    sql: str
    columns: list[str]
    type_overrides: dict[str, str] = field(default_factory=dict)
    count_unit: dict | None = None


def compile_op(op: dict, src: str, columns: list[str], col_types: dict[str, str]) -> Compiled:
    """Compile one validated op into a SELECT over `src` (a table or subquery name)."""
    k = op["op"]
    frm = f"FROM {src}"
    if k == "mark_missing":
        col = op["column"]
        expr = f"CASE WHEN trim({ident(col)}) IN {lit_list(op['values'])} THEN NULL ELSE {ident(col)} END"
        return Compiled(f"SELECT {_select(columns, {col: expr})} {frm}", columns)
    if k == "fill_blank":
        col = op["column"]
        expr = f"CASE WHEN {ident(col)} IS NULL OR trim({ident(col)}) = '' THEN {lit(str(op['value']))} ELSE {ident(col)} END"
        return Compiled(f"SELECT {_select(columns, {col: expr})} {frm}", columns)
    if k == "change_type":
        col = op["column"]
        sql = f"SELECT {_select(columns, {col: _change_type_expr(col, op['to'])})} {frm}"
        return Compiled(sql, columns, type_overrides={col: op["to"]})
    if k == "split_column":
        col, sep = op["column"], op["sep"]
        a, b = op["into"]
        c = ident(col)
        first = f"CASE WHEN strpos({c}, {lit(sep)}) > 0 THEN split_part({c}, {lit(sep)}, 1) ELSE {c} END"
        second = f"CASE WHEN strpos({c}, {lit(sep)}) > 0 THEN substr({c}, strpos({c}, {lit(sep)}) + {len(sep)}) END"
        new_cols, parts = [], [ROW_ID]
        for name in columns:
            if name == col:
                new_cols += [a, b]
                parts += [f"{first} AS {ident(a)}", f"{second} AS {ident(b)}"]
            elif name not in (a, b):
                new_cols.append(name)
                parts.append(ident(name))
        return Compiled(f"SELECT {', '.join(parts)} {frm}", new_cols)
    if k == "recode_values":
        col = op["column"]
        whens = " ".join(f"WHEN {lit(a)} THEN {lit(b)}" for a, b in op["mapping"].items())
        expr = f"CASE {ident(col)} {whens} ELSE {ident(col)} END"
        return Compiled(f"SELECT {_select(columns, {col: expr})} {frm}", columns)
    if k == "merge_values":
        col = op["column"]
        expr = f"CASE WHEN {ident(col)} IN {lit_list(op['from'])} THEN {lit(op['to'])} ELSE {ident(col)} END"
        return Compiled(f"SELECT {_select(columns, {col: expr})} {frm}", columns)
    if k == "combine_columns":
        srcs, into = op["columns"], op["into"]
        expr = f"concat_ws({lit(op['sep'])}, {', '.join(ident(s) for s in srcs)})"
        new_cols, parts = [], [ROW_ID]
        for name in columns:
            if name == srcs[0]:
                new_cols.append(into)
                parts.append(f"NULLIF({expr}, '') AS {ident(into)}")
            elif name not in srcs and name != into:
                new_cols.append(name)
                parts.append(ident(name))
        return Compiled(f"SELECT {', '.join(parts)} {frm}", new_cols)
    if k == "set_count_unit":
        return Compiled(f"SELECT * {frm}", columns, count_unit={"columns": op["columns"], "label": op["label"]})
    if k == "drop_rows":
        return Compiled(f"SELECT * {frm} WHERE NOT ({where_sql(op['where'], col_types)})", columns)
    if k == "flag_rows":
        cols, select = _with_flag(columns, where_sql(op["where"], col_types), op["label"])
        return Compiled(f"SELECT {select} {frm}", cols)
    if k == "remove_duplicates":
        key = op["columns"] or [c for c in columns if c != FLAG_COLUMN]
        part = ", ".join(ident(c) for c in key)
        return Compiled(f"SELECT * {frm} QUALIFY row_number() OVER (PARTITION BY {part} ORDER BY {ROW_ID}) = 1", columns)
    if k == "merge_records":
        part = ", ".join(ident(c) for c in op["key"])
        order = "ASC" if op["keep"] == "first" else "DESC"
        any_null = " OR ".join(f"{ident(c)} IS NULL" for c in op["key"])
        sql = (f"SELECT * {frm} QUALIFY ({any_null}) OR "
               f"row_number() OVER (PARTITION BY {part} ORDER BY {ROW_ID} {order}) = 1")
        return Compiled(sql, columns)
    if k == "keep_separate":
        return Compiled(f"SELECT * {frm}", columns)
    if k == "flag_duplicates":
        part = ", ".join(ident(c) for c in op["key"])
        not_null = " AND ".join(f"{ident(c)} IS NOT NULL" for c in op["key"])
        cond = f"({not_null} AND count(*) OVER (PARTITION BY {part}) > 1)"
        cols, select = _with_flag(columns, cond, op["label"])
        return Compiled(f"SELECT {select} {frm}", cols)
    raise OpError(f"Unknown op '{k}'")


def op_columns(op: dict) -> list[str]:
    """Columns an op is about (used for previews and issue matching)."""
    if "column" in op:
        return [op["column"]]
    for key in ("columns", "key"):
        if op.get(key):
            return list(op[key])
    if op.get("where"):
        return [f["column"] for f in op["where"]]
    return []
