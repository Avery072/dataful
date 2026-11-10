"""Value-level problems: disguised blanks, junk, defaults posing as data, impossible values,
outliers, gaps, and columns that carry no information."""

from __future__ import annotations

from datetime import date

from .. import store
from ..profile import has_token
from ..sql import JUNK_TOKENS, MISSING_TOKENS, date_expr, ident, is_blank, lit, lit_list, not_blank, num
from .base import Context, Issue, are, count_of, issue_id, keep_option, n, numeric_like, option, pct, quote_values

GENERIC_DEFAULTS = {"other", "others", "unknown", "default", "none", "misc", "miscellaneous", "general",
                    "not specified", "unspecified", "not set", "select", "-- select --"}
NUMERIC_DEFAULTS = (0.0, 1.0, -1.0, 99.0, 999.0, 9999.0, 99999.0)
NON_NEGATIVE_TOKENS = {"age", "height", "weight", "price", "amount", "quantity", "qty", "salary", "pages", "count",
                       "phone", "distance", "duration", "year", "rating", "units", "copies", "staff", "size",
                       "population", "revenue", "cost", "number", "length", "width", "mobile", "tel"}
PHONE_TOKENS = {"phone", "tel", "mobile", "fax"}
ZERO_MEANING_TOKENS = {"discount", "fee", "tax", "bonus", "refund", "qty", "quantity", "units", "copies",
                       "commission", "tip", "shipping", "returns", "overtime"}
JUNK_PATTERN = r"^[0\s().+-]{7,}$"   # 000-000-0000, (000) 000-0000


def _value_counts(ctx: Context, col: str, condition: str, limit: int = 50) -> list[tuple[str, int]]:
    return store.query(f"SELECT trim({ident(col)}) v, count(*) c FROM {ctx.t} WHERE {condition} "
                       f"GROUP BY v ORDER BY c DESC LIMIT {limit}")


# ---------- disguised missing ----------

def disguised_missing(ctx: Context) -> list[Issue]:
    issues = []
    tokens = lit_list(t for t in MISSING_TOKENS if t)
    for col in ctx.columns:
        found = _value_counts(ctx, col, f"{ident(col)} IS NOT NULL AND lower(trim({ident(col)})) IN {tokens}")
        found += [(v, c) for v, c in _value_counts(ctx, col, f"{ident(col)} IS NOT NULL AND trim({ident(col)}) = ''")]
        if not found:
            continue
        values = [v for v, _ in found]
        total = sum(c for _, c in found)
        shown = " / ".join(f"'{v}'" for v in values[:3])
        issues.append(Issue(
            id=issue_id("disguised_missing", col), family="disguised_missing",
            title=f"{count_of(total, 'cell')} in {col} {'says' if total == 1 else 'say'} {shown} instead of being blank",
            detail="These are placeholders for 'no value'. Left as text they are counted as a real category "
                   "and stop the column from being read as numbers or dates.",
            severity="missing", confidence="certain", columns=[col], affected_rows=total, kind="fix",
            options=[option("Treat as missing", {"op": "mark_missing", "column": col, "values": values})],
            evidence_for=[f"'{v}' appears {count_of(c, 'time')}" for v, c in found[:4]],
            flag_expr=f"trim({ident(col)}) IN {lit_list(values)}", flag_column=col))
    return issues


def junk_values(ctx: Context) -> list[Issue]:
    """Placeholders that look like data: 'asdf', 'test', '000-000-0000'."""
    issues = []
    for c in ctx.cols("identifier", "category", "text", "geo"):
        cond = (f"{ident(c.name)} IS NOT NULL AND (lower(trim({ident(c.name)})) IN {lit_list(JUNK_TOKENS)} "
                f"OR regexp_matches(trim({ident(c.name)}), {lit(JUNK_PATTERN)}))")
        found = _value_counts(ctx, c.name, cond)
        total = sum(k for _, k in found)
        if not found or total > 0.05 * ctx.rows:
            continue
        values = [v for v, _ in found]
        issues.append(Issue(
            id=issue_id("disguised_missing", c.name, "junk"), family="disguised_missing",
            title=f"{count_of(total, c.name + ' value')} {'looks' if total == 1 else 'look'} like placeholders ({quote_values(values, 2)})",
            detail="Typed to get past a required field. They look like real values, so they slip into counts and matches.",
            severity="missing", confidence="likely", columns=[c.name], affected_rows=total, kind="question",
            question=f"Are {quote_values(values)} real {c.name} values?",
            options=[option("No, treat as missing", {"op": "mark_missing", "column": c.name, "values": values}),
                     option("Flag those rows", {"op": "flag_rows", "label": "Placeholder value",
                                                "where": [{"column": c.name, "op": "in", "value": values}]}),
                     keep_option("Yes, keep them")],
            evidence_for=[f"'{v}' appears {count_of(k, 'time')}" for v, k in found[:4]],
            flag_expr=f"trim({ident(c.name)}) IN {lit_list(values)}", flag_column=c.name))
    return issues


# ---------- defaults posing as data ----------

def default_values(ctx: Context) -> list[Issue]:
    return _generic_default(ctx) + _date_default(ctx) + _numeric_default(ctx)


def _generic_default(ctx: Context) -> list[Issue]:
    issues = []
    for c in ctx.cols("category"):
        if not c.top_nonblank:
            continue
        value, count = c.top_nonblank[0]
        share = count / c.nonblank if c.nonblank else 0
        if str(value).strip().lower() not in GENERIC_DEFAULTS or share < 0.4:
            continue
        issues.append(Issue(
            id=issue_id("default_values", c.name), family="default_values",
            title=f"{pct(count, c.nonblank)} of {c.name} is '{value}'",
            detail=f"A catch-all value this common usually means nobody filled the field in, "
                   f"so any breakdown by {c.name} is mostly unknown.",
            severity="missing", confidence="likely", columns=[c.name], affected_rows=count, kind="question",
            question=f"Does '{value}' in {c.name} mean a real category, or 'not recorded'?",
            options=[option("It means not recorded", {"op": "mark_missing", "column": c.name, "values": [value]}),
                     keep_option("It's a real category")],
            evidence_for=[f"'{value}' is {n(count)} of {n(c.nonblank)} rows",
                          f"Next most common value: {c.top_nonblank[1][0]!r} ({n(c.top_nonblank[1][1])})"
                          if len(c.top_nonblank) > 1 else "No other common value"],
            flag_expr=f"trim({ident(c.name)}) = {lit(value)}", flag_column=c.name))
    return issues


def _date_default(ctx: Context) -> list[Issue]:
    """Jan 1 (or another single day) far more common than any normal day."""
    issues = []
    for c in ctx.cols("time"):
        if c.type != "date" or c.nonblank < 100:
            continue
        d = date_expr(c.name)
        jan1, days = store.query(f"SELECT count(*) FILTER (WHERE month({d}) = 1 AND day({d}) = 1), "
                                 f"count(DISTINCT CAST({d} AS DATE)) FROM {ctx.t} WHERE {not_blank(c.name)}")[0]
        expected = c.nonblank / max(days, 1)
        if jan1 < 0.02 * c.nonblank or jan1 < 10 * expected:
            continue
        values = [v for v, _ in _value_counts(ctx, c.name, f"month({d}) = 1 AND day({d}) = 1")]
        issues.append(Issue(
            id=issue_id("default_values", c.name, "jan1"), family="default_values",
            title=f"{count_of(jan1, c.name + ' value')} {'falls' if jan1 == 1 else 'fall'} on January 1",
            detail="Systems often fill an unknown date with Jan 1. These rows would pile up at the start of each year in any trend.",
            severity="missing", confidence="likely", columns=[c.name], affected_rows=jan1, kind="question",
            question=f"Is January 1 a real {c.name}, or a placeholder?",
            options=[option("Placeholder — treat as missing", {"op": "mark_missing", "column": c.name, "values": values}),
                     option("Flag those rows", {"op": "flag_rows", "label": f"{c.name} is Jan 1",
                                                "where": [{"column": c.name, "op": "in", "value": values}]}),
                     keep_option("They're real dates")],
            evidence_for=[f"{n(jan1)} rows on Jan 1 vs about {expected:.0f} on a typical day"],
            flag_expr=f"trim({ident(c.name)}) IN {lit_list(values)}", flag_column=c.name))
    return issues


def _numeric_default(ctx: Context) -> list[Issue]:
    issues = []
    for c in ctx.cols("measure"):
        if c.distinct < 20:
            continue
        row = store.query(f"SELECT {num(c.name)} v, count(*) k FROM {ctx.t} WHERE {not_blank(c.name)} "
                          f"GROUP BY v ORDER BY k DESC LIMIT 1")
        if not row or row[0][0] not in NUMERIC_DEFAULTS or row[0][1] < 0.3 * c.nonblank:
            continue
        value, count = row[0]
        shown = f"{value:g}"
        issues.append(Issue(
            id=issue_id("default_values", c.name, shown), family="default_values",
            title=f"{pct(count, c.nonblank)} of {c.name} is exactly {shown}",
            detail=f"One value this common in a varied number column often means 'not entered'. It drags averages toward {shown}.",
            severity="numbers", confidence="guess", columns=[c.name], affected_rows=count, kind="question",
            question=f"Is {c.name} = {shown} a real value?",
            options=[option("No, treat as missing", {"op": "mark_missing", "column": c.name,
                                                     "values": [v for v, _ in _value_counts(ctx, c.name, f"{num(c.name)} = {value}")]}),
                     keep_option("Yes, it's real")],
            evidence_for=[f"{n(count)} of {n(c.nonblank)} rows are {shown}"],
            flag_expr=f"{num(c.name)} = {value}", flag_column=c.name))
    return issues


# ---------- impossible values ----------

def impossible_values(ctx: Context) -> list[Issue]:
    issues = []
    for c in ctx.columns:
        info = ctx.info[c]
        if not numeric_like(info) or info.type == "date" or not has_token(c, NON_NEGATIVE_TOKENS):
            continue
        negative = store.query(f"SELECT count(*), min({num(c)}) FROM {ctx.t} WHERE {num(c)} < 0")[0]
        if negative[0]:
            issues.append(_negative_issue(ctx, c, negative[0], negative[1]))
        if has_token(c, {"age"}):
            old = store.query(f"SELECT count(*), max({num(c)}) FROM {ctx.t} WHERE {num(c)} > 120")[0]
            if old[0]:
                issues.append(_range_issue(ctx, c, old[0], f"{old[1]:g}", "> 120", ">", 120))
    return issues + _future_dates(ctx)


MAX_LISTED_VALUES = 5000   # a mark_missing op lists values; beyond this, offer flagging only


def _negative_issue(ctx: Context, col: str, count: int, lowest: float) -> Issue:
    where = [{"column": col, "op": "<", "value": 0}]
    flag = option("Flag those rows", {"op": "flag_rows", "label": f"Negative {col}", "where": where})
    every = count == ctx.info[col].nonblank
    title = f"Every {col} value is negative" if every else f"{count_of(count, 'row')} have a negative {col}"
    if has_token(col, PHONE_TOKENS):
        # The minus sign means the number was mangled on export; the real phone number can't be recovered,
        # so the honest fixes are to stop treating it as data (missing) or to flag it, not to re-type it.
        options = [flag, keep_option()]
        damaged = _value_counts(ctx, col, f"{num(col)} < 0", limit=MAX_LISTED_VALUES + 1)
        if len(damaged) <= MAX_LISTED_VALUES:
            options.insert(0, option(f"Treat negative {col} values as missing",
                                     {"op": "mark_missing", "column": col, "values": [v for v, _ in damaged]},
                                     "The real numbers can't be recovered from this file, so they become blanks."))
        detail = (f"A phone number can't be negative: {col} was stored as a number and damaged on export, "
                  "so these values can't be used to call or match anyone.")
    else:
        options = [flag, option("Exclude those rows", {"op": "drop_rows", "where": where}), keep_option()]
        detail = f"{col} can't be below zero, so these are entry or export errors and will skew totals and averages."
    return Issue(
        id=issue_id("impossible_values", col, "negative"), family="impossible_values",
        title=title, detail=detail, severity="numbers", confidence="certain", columns=[col], affected_rows=count,
        kind="question", question=f"What should happen to negative {col} values?", options=options,
        evidence_for=[f"Lowest value: {lowest:,.0f}", f"{n(count)} of {n(ctx.rows)} rows ({pct(count, ctx.rows)})"],
        flag_expr=f"{num(col)} < 0", flag_column=col)


def _range_issue(ctx: Context, col: str, count: int, extreme: str, label: str, op: str, bound: float) -> Issue:
    where = [{"column": col, "op": op, "value": bound}]
    return Issue(
        id=issue_id("impossible_values", col, "range"), family="impossible_values",
        title=f"{count_of(count, 'row')} {'has' if count == 1 else 'have'} {col} {label}", detail=f"Values like {extreme} are not plausible for {col}.",
        severity="numbers", confidence="likely", columns=[col], affected_rows=count, kind="question",
        question=f"What should happen to rows with {col} {label}?",
        options=[option("Flag them", {"op": "flag_rows", "where": where, "label": f"Implausible {col}"}),
                 option("Exclude them", {"op": "drop_rows", "where": where}), keep_option()],
        evidence_for=[f"Most extreme value: {extreme}"], flag_expr=f"{num(col)} {op} {bound}", flag_column=col)


def _future_dates(ctx: Context) -> list[Issue]:
    """A few dates in the future among mostly past dates usually means typos (2032 for 2023)."""
    issues = []
    today = date.today().isoformat()
    for c in ctx.cols("time"):
        if c.type != "date" or has_token(c.name, {"close", "due", "end", "expected", "expiry", "expires", "renewal"}):
            continue
        future = store.query(f"SELECT count(*), max({date_expr(c.name)}) FROM {ctx.t} "
                             f"WHERE {date_expr(c.name)} > TIMESTAMP {lit(today)}")[0]
        if not future[0] or future[0] > 0.05 * c.nonblank:
            continue
        where = [{"column": c.name, "op": ">", "value": today}]
        issues.append(Issue(
            id=issue_id("impossible_values", c.name, "future"), family="impossible_values",
            title=f"{count_of(future[0], c.name + ' value')} {are(future[0])} in the future",
            detail=f"Most {c.name} values are in the past; these few look like typos.",
            severity="numbers", confidence="likely", columns=[c.name], affected_rows=future[0], kind="question",
            question=f"Are future {c.name} values mistakes?",
            options=[option("Flag them", {"op": "flag_rows", "where": where, "label": f"Future {c.name}"}),
                     option("Exclude them", {"op": "drop_rows", "where": where}), keep_option("They're fine")],
            evidence_for=[f"Latest: {str(future[1])[:10]}"],
            flag_expr=f"{date_expr(c.name)} > TIMESTAMP {lit(today)}", flag_column=c.name))
    return issues


# ---------- outliers ----------

def outliers(ctx: Context) -> list[Issue]:
    issues = []
    for c in ctx.cols("measure"):
        if c.distinct < 10 or not c.is_numeric:
            continue
        q1, q3 = store.query(f"SELECT quantile_cont(v, 0.25), quantile_cont(v, 0.75) FROM "
                             f"(SELECT {num(c.name)} v FROM {ctx.t}) WHERE v IS NOT NULL")[0]
        iqr = (q3 or 0) - (q1 or 0)
        if not iqr:
            continue
        lo, hi = q1 - 3 * iqr, q3 + 3 * iqr
        high, low, top = store.query(f"SELECT count(*) FILTER (WHERE {num(c.name)} > {hi}), "
                                     f"count(*) FILTER (WHERE {num(c.name)} < {lo}), max({num(c.name)}) FROM {ctx.t}")[0]
        if not (high or low) or high + low > 0.02 * c.nonblank:
            continue
        op, bound, count = (">", hi, high) if high >= low else ("<", lo, low)
        where = [{"column": c.name, "op": op, "value": round(bound, 4)}]
        word = "above" if op == ">" else "below"
        issues.append(Issue(
            id=issue_id("outliers", c.name), family="outliers",
            title=f"{count_of(count, c.name + ' value')} {are(count)} far {word} the rest",
            detail=f"Typical {c.name} is {q1:,.4g}–{q3:,.4g}. Extreme values can be real, but they move averages a lot.",
            severity="numbers", confidence="guess", columns=[c.name], affected_rows=count, kind="question",
            question=f"Are {c.name} values {word} {bound:,.4g} real?",
            options=[option("Flag them for review", {"op": "flag_rows", "where": where, "label": f"Unusual {c.name}"}),
                     option("Exclude them", {"op": "drop_rows", "where": where}), keep_option("They're real")],
            evidence_for=[f"{n(count)} values {word} {bound:,.4g} (3× the middle range)", f"Largest: {top:,.4g}"],
            evidence_against=["Rare but genuine extremes look exactly like this"],
            flag_expr=f"({num(c.name)} > {hi} OR {num(c.name)} < {lo})", flag_column=c.name))
    return issues


# ---------- gaps ----------

def missing_values(ctx: Context) -> list[Issue]:
    issues = []
    for c in ctx.cols("measure", "time", "geo", "identifier"):
        if c.missing_pct <= 0.05 or c.nonblank == 0:
            continue
        if c.role == "measure" and has_token(c.name, ZERO_MEANING_TOKENS):
            issues.append(_blank_means_zero(c, ctx))
            continue
        where = [{"column": c.name, "op": "is_missing"}]
        issues.append(Issue(
            id=issue_id("missing_values", c.name), family="missing_values",
            title=f"{c.name} is blank for {pct(c.missing, c.rows)} of rows",
            detail=f"{count_of(c.missing, 'row')} {'has' if c.missing == 1 else 'have'} no {c.name}. "
                   "Averages and charts silently skip them.",
            severity="missing", confidence="certain", columns=[c.name], affected_rows=c.missing, kind="question",
            question=f"How should rows with no {c.name} be handled?",
            options=[keep_option("Leave them blank", "Rows stay; they're skipped in averages."),
                     option("Flag them", {"op": "flag_rows", "where": where, "label": f"No {c.name}"}),
                     option("Exclude them", {"op": "drop_rows", "where": where})],
            evidence_for=[f"{n(c.missing)} of {n(c.rows)} rows are blank or a placeholder"],
            flag_expr=is_blank(c.name), flag_column=c.name))
    return issues


def _blank_means_zero(c, ctx: Context) -> Issue:
    return Issue(
        id=issue_id("missing_values", c.name, "zero"), family="missing_values",
        title=f"{c.name} is blank for {pct(c.missing, c.rows)} of rows",
        detail=f"For a field like {c.name}, blank often means 'none' (0) — or it may really be unknown. "
               "The answer changes every average.",
        severity="numbers", confidence="guess", columns=[c.name], affected_rows=c.missing, kind="question",
        question=f"Does a blank {c.name} mean 0, or unknown?",
        options=[option("Blank means 0", {"op": "fill_blank", "column": c.name, "value": 0}),
                 keep_option("Unknown — leave blank")],
        evidence_for=[f"{n(c.missing)} of {n(c.rows)} rows are blank",
                      f"Filled-in values range {c.min}–{c.max}"],
        flag_expr=is_blank(c.name), flag_column=c.name)


def constant_column(ctx: Context) -> list[Issue]:
    issues = []
    for col in ctx.columns:
        c = ctx.info[col]
        if c.distinct > 1:
            continue
        empty = c.nonblank == 0
        value = None if empty else c.top_nonblank[0][0] if c.top_nonblank else None
        issues.append(Issue(
            id=issue_id("constant_column", col), family="constant_column",
            title=f"{col} is empty" if empty else f"Every row has the same {col} ('{value}')",
            detail="This column carries no information; it can be ignored in analysis.",
            severity="format", confidence="certain", columns=[col], affected_rows=0, kind="question",
            question=None, options=[keep_option("Got it")]))
    return issues
