"""Business-logic checks that still work on any table: test records, mixed currencies,
contradictory states (won at $0, open but past close date), and stale activity."""

from __future__ import annotations

import re
from datetime import date, timedelta

from .. import store
from ..profile import has_token
from ..sql import date_expr, ident, lit, lit_list, not_blank, num
from .base import Context, Issue, is_money, issue_id, keep_option, n, numeric_like, option, quote_values

TEST_PATTERN = r"(?i)(\btest\b|\btesting\b|\bdummy\b|internal|\bsandbox\b|do not use|\bfake\b)"
CURRENCIES = {"usd", "eur", "gbp", "jpy", "cad", "aud", "chf", "cny", "inr", "sek", "nok", "dkk", "nzd", "mxn", "brl"}
WON_PATTERN = r"(?i)\b(won|paid|completed?|closed[ -]?won|delivered)\b"
CLOSED_PATTERN = r"(?i)\b(won|lost|closed|paid|completed?|cancell?ed|delivered)\b"
STALE_TOKENS = {"last", "updated", "modified", "activity", "contacted", "seen", "touched"}


def test_records(ctx: Context) -> list[Issue]:
    issues = []
    for c in ctx.cols("identifier", "category"):  # not free text: a film called "Test Pilot" is fine
        if c.type != "text":
            continue
        found = store.query(f"SELECT {ident(c.name)}, count(*) k FROM {ctx.t} WHERE {not_blank(c.name)} "
                            f"AND regexp_matches({ident(c.name)}, {lit(TEST_PATTERN)}) GROUP BY 1 ORDER BY k DESC LIMIT 50")
        total = sum(k for _, k in found)
        if not found or total > 0.1 * ctx.rows:
            continue
        values = [v for v, _ in found]
        where = [{"column": c.name, "op": "in", "value": values}]
        issues.append(Issue(
            id=issue_id("test_records", c.name), family="test_records",
            title=f"{n(total)} rows look like test or internal records",
            detail=f"{c.name} values like {quote_values(values, 2)} usually mark test data or your own team, "
                   "not real customers. They inflate counts and totals.",
            severity="numbers", confidence="likely", columns=[c.name], affected_rows=total, kind="question",
            question=f"Are rows with {c.name} like {quote_values(values, 2)} real?",
            options=[option("No, exclude them", {"op": "drop_rows", "where": where}),
                     option("Flag them", {"op": "flag_rows", "where": where, "label": "Test / internal"}),
                     keep_option("Yes, they're real")],
            evidence_for=[f"'{v}' appears {n(k)} times" for v, k in found[:3]],
            flag_expr=f"{ident(c.name)} IN {lit_list(values)}", flag_column=c.name))
    return issues


def mixed_units(ctx: Context) -> list[Issue]:
    """Amounts in several currencies added together."""
    money = [c for c in ctx.columns if is_money(ctx.info[c]) and numeric_like(ctx.info[c])]
    if not money:
        return []
    issues = []
    for c in ctx.cols("category"):
        values = [str(v).lower() for v, _ in c.top_nonblank]
        if not (has_token(c.name, {"currency", "ccy", "cur"}) or (values and set(values) <= CURRENCIES)):
            continue
        if c.distinct < 2:
            continue
        top = c.top_nonblank
        main = top[0][0]
        where = [{"column": c.name, "op": "!=", "value": main}]
        others = sum(k for _, k in top[1:])
        issues.append(Issue(
            id=issue_id("mixed_units", c.name), family="mixed_units",
            title=f"{money[0]} mixes currencies ({', '.join(f'{v} {n(k)}' for v, k in top[:3])})",
            detail=f"Adding {money[0]} across rows sums different currencies as if they were the same.",
            severity="numbers", confidence="likely", columns=[money[0], c.name], affected_rows=others, kind="question",
            question=f"How should non-{main} amounts be handled?",
            options=[option(f"Only use {main} rows", {"op": "drop_rows", "where": where}),
                     option(f"Flag non-{main} rows", {"op": "flag_rows", "where": where, "label": f"Not {main}"}),
                     keep_option("Keep all (I'll convert separately)")],
            evidence_for=[f"{c.name} has {c.distinct} currencies", f"{n(others)} rows are not {main}"],
            flag_expr=f"{ident(c.name)} IS DISTINCT FROM {lit(main)}", flag_column=money[0]))
    return issues


def _status_column(ctx: Context):
    """A category column that holds outcomes like 'Closed Won' / 'Lost'."""
    for c in ctx.cols("category"):
        if c.distinct > 30 or c.type != "text":
            continue
        values = [r[0] for r in store.query(f"SELECT {ident(c.name)} FROM {ctx.t} WHERE {not_blank(c.name)} "
                                            f"GROUP BY 1 ORDER BY count(*) DESC")]
        closed = [v for v in values if re.search(CLOSED_PATTERN, v)]
        if closed and len(closed) < len(values):
            won = [v for v in closed if re.search(WON_PATTERN, v)]
            return c.name, values, closed, won
    return None


def contradictions(ctx: Context) -> list[Issue]:
    status = _status_column(ctx)
    if not status:
        return []
    col, values, closed, won = status
    issues = []
    money = next((m for m in ctx.columns if is_money(ctx.info[m]) and numeric_like(ctx.info[m])), None)
    if money and won:
        zero = store.query(f"SELECT count(*) FROM {ctx.t} WHERE {ident(col)} IN {lit_list(won)} AND {num(money)} = 0")[0][0]
        if zero:
            where = [{"column": col, "op": "in", "value": won}, {"column": money, "op": "<", "value": 0.01}]
            issues.append(Issue(
                id=issue_id("impossible_values", col, money, "won_zero"), family="impossible_values",
                title=f"{n(zero)} rows are {won[0]} with {money} 0",
                detail=f"A {won[0]} outcome with no {money} contradicts itself — usually an amount that was never entered.",
                severity="numbers", confidence="likely", columns=[col, money], affected_rows=zero, kind="question",
                question=f"What should happen to {won[0]} rows with {money} 0?",
                options=[option("Flag them", {"op": "flag_rows", "where": where, "label": f"{won[0]} at 0"}),
                         option("Exclude them", {"op": "drop_rows", "where": where}), keep_option()],
                evidence_for=[f"{n(zero)} rows where {col} is {quote_values(won, 2)} and {money} is 0"],
                flag_expr=f"({ident(col)} IN {lit_list(won)} AND {num(money)} = 0)", flag_column=money))
    due = next((c.name for c in ctx.cols("time") if c.type == "date"
                and has_token(c.name, {"close", "due", "end", "expected", "deadline"})), None)
    open_values = [v for v in values if v not in closed]
    if due and open_values:
        today = date.today().isoformat()
        cond = f"{ident(col)} IN {lit_list(open_values)} AND {date_expr(due)} < TIMESTAMP {lit(today)}"
        past = store.query(f"SELECT count(*) FROM {ctx.t} WHERE {cond}")[0][0]
        if past:
            where = [{"column": col, "op": "in", "value": open_values}, {"column": due, "op": "<", "value": today}]
            issues.append(Issue(
                id=issue_id("impossible_values", col, due, "overdue"), family="impossible_values",
                title=f"{n(past)} open rows have a {due} in the past",
                detail=f"Still {quote_values(open_values, 2)} but {due} has passed — the pipeline is out of date, "
                       "so forecasts built on it are inflated.",
                severity="numbers", confidence="likely", columns=[col, due], affected_rows=past, kind="question",
                question=f"How should open rows with a past {due} be treated?",
                options=[option("Flag them as overdue", {"op": "flag_rows", "where": where, "label": "Overdue"}),
                         option("Exclude them", {"op": "drop_rows", "where": where}), keep_option()],
                evidence_for=[f"{n(past)} rows with {col} in {quote_values(open_values, 2)} and {due} before {today}"],
                flag_expr=f"({cond})", flag_column=due))
    return issues


def stale_data(ctx: Context) -> list[Issue]:
    """Open records with no activity for a year, or an export whose newest activity is months old."""
    issues = []
    status = _status_column(ctx)
    for c in ctx.cols("time"):
        if c.type != "date" or not has_token(c.name, STALE_TOKENS):
            continue
        newest = store.query(f"SELECT max({date_expr(c.name)}) FROM {ctx.t}")[0][0]
        if newest is None:
            continue
        if status:
            issue = _stale_open_rows(ctx, c.name, newest.date(), status)
        else:
            issue = _stale_export(ctx, c.name, newest.date())
        if issue:
            issues.append(issue)
    return issues


def _stale_open_rows(ctx: Context, col: str, newest: date, status) -> Issue | None:
    status_col, values, closed, _ = status
    open_values = [v for v in values if v not in closed]
    cutoff = (newest - timedelta(days=365)).isoformat()
    cond = f"{ident(status_col)} IN {lit_list(open_values)} AND {date_expr(col)} < TIMESTAMP {lit(cutoff)}"
    old = store.query(f"SELECT count(*) FROM {ctx.t} WHERE {cond}")[0][0]
    if not old:
        return None
    where = [{"column": status_col, "op": "in", "value": open_values}, {"column": col, "op": "<", "value": cutoff}]
    return Issue(
        id=issue_id("stale_data", col), family="stale_data",
        title=f"{n(old)} open rows have had no {col} for over a year",
        detail=f"They are still {quote_values(open_values, 2)}, but their {col} is more than a year before the newest "
               f"one ({newest}). They are probably dead, yet still counted as open.",
        severity="missing", confidence="guess", columns=[col, status_col], affected_rows=old, kind="question",
        question=f"Should open rows with {col} before {cutoff} still count as open?",
        options=[option("Flag them as stale", {"op": "flag_rows", "where": where, "label": "Stale"}),
                 option("Exclude them", {"op": "drop_rows", "where": where}), keep_option("Yes, keep them")],
        evidence_for=[f"{n(old)} open rows with {col} before {cutoff}"],
        flag_expr=f"({cond})", flag_column=col)


def _stale_export(ctx: Context, col: str, newest: date) -> Issue | None:
    age = (date.today() - newest).days
    if age < 180:
        return None
    return Issue(
        id=issue_id("stale_data", col, "export"), family="stale_data",
        title=f"The newest {col} is {age // 30} months old",
        detail=f"Nothing in this file is more recent than {newest}. Numbers may not reflect the current state.",
        severity="missing", confidence="guess", columns=[col], affected_rows=0, kind="question",
        question=None, options=[keep_option("Got it")],
        evidence_for=[f"Newest {col}: {newest}"])
