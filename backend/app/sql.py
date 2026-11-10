"""Small SQL-building helpers shared by every module (quoting, literals, parsing expressions)."""

from __future__ import annotations

from typing import Iterable

ROW_ID = "__rid"  # hidden, stable row number carried through every view

# Values people type when they mean "nothing here". Compared after lower(trim()).
MISSING_TOKENS: tuple[str, ...] = (
    "", "na", "n/a", "n.a.", "nan", "null", "none", "nil", "-", "--", "?",
    "tbd", "tba", "unknown", "missing", "#n/a", "not available", "(blank)",
)
# Junk that looks like a real value but is a placeholder. Compared after lower(trim()).
JUNK_TOKENS: tuple[str, ...] = (
    "asdf", "qwerty", "xxx", "xxxx", "test", "dummy", "sample", "placeholder",
    "lorem ipsum", "000-000-0000", "0000000000", "(000) 000-0000",
    "123-456-7890", "test@test.com",
)


def ident(name: str) -> str:
    """Quote an identifier for DuckDB."""
    return '"' + name.replace('"', '""') + '"'


def lit(value: object) -> str:
    """Render a Python value as a SQL literal (strings are always escaped)."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def lit_list(values: Iterable[object]) -> str:
    items = [lit(v) for v in values]
    return "(" + ", ".join(items) + ")" if items else "(NULL)"


def is_blank(col: str) -> str:
    """True when a cell is empty or holds a disguised-missing token like 'NA'."""
    return f"({ident(col)} IS NULL OR lower(trim({ident(col)})) IN {lit_list(MISSING_TOKENS)})"


def not_blank(col: str) -> str:
    return f"(NOT {is_blank(col)})"


def num(col: str) -> str:
    """Parse a cell as a number, tolerating currency symbols, thousands separators and %."""
    c = ident(col)
    return f"TRY_CAST(regexp_replace(trim({c}), '[$€£¥,%\\s]', '', 'g') AS DOUBLE)"


def plain_num(col: str) -> str:
    """Parse a cell as a number with no cleanup (detects text-stored numbers)."""
    return f"TRY_CAST(trim({ident(col)}) AS DOUBLE)"


DATE_FORMATS = ("%m/%d/%Y", "%d.%m.%Y", "%Y/%m/%d", "%m/%d/%y", "%d-%b-%Y", "%b %d, %Y")


def date_expr(col: str) -> str:
    """Parse a cell as a timestamp, trying ISO first and then common spreadsheet formats."""
    c = f"trim({ident(col)})"
    parts = [f"TRY_CAST({c} AS TIMESTAMP)"] + [f"try_strptime({c}, {lit(f)})" for f in DATE_FORMATS]
    return "COALESCE(" + ", ".join(parts) + ")"
