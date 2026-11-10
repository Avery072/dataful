"""Format damage and shape problems: numbers stored as text, dates as text or epoch seconds,
whole numbers stored as decimals, two fields packed into one, one field split into two."""

from __future__ import annotations

import re

from .. import store
from ..profile import TIME_TOKENS, has_token
from ..sql import ident, lit, not_blank, num, plain_num
from .base import Context, Issue, issue_id, keep_option, n, option, pct

SEPARATORS = (" - ", " | ", "-", "_", "/", "|", ":", ";")


def text_numbers(ctx: Context) -> list[Issue]:
    """'$12,500' and '12500' in one column: totals and sorting both break."""
    issues = []
    for c in ctx.columns:
        info = ctx.info[c]
        if info.type != "text" or info.role == "identifier" or not info.nonblank:
            continue
        if info.n_num_clean < 0.9 * info.nonblank or info.n_num_clean == info.n_num:
            continue
        examples = store.query(f"SELECT {ident(c)} FROM {ctx.t} WHERE {not_blank(c)} AND {plain_num(c)} IS NULL "
                               f"AND {num(c)} IS NOT NULL GROUP BY 1 ORDER BY count(*) DESC LIMIT 3")
        damaged = info.n_num_clean - info.n_num
        issues.append(Issue(
            id=issue_id("format_damage", c, "text_number"), family="format_damage",
            title=f"{c} is numbers stored as text",
            detail=f"{n(damaged)} values carry symbols or separators (like {', '.join(repr(e[0]) for e in examples)}), "
                   "so the column can't be summed or sorted as numbers.",
            severity="numbers", confidence="certain", columns=[c], affected_rows=damaged, kind="fix",
            options=[option("Convert to numbers", {"op": "change_type", "column": c, "to": "decimal"})],
            evidence_for=[f"{pct(info.n_num_clean, info.nonblank)} of values are numbers once '$' and ',' are removed"],
            evidence_against=[f"{n(info.nonblank - info.n_num_clean)} values still aren't numbers and would become blank"]
            if info.n_num_clean < info.nonblank else [],
            flag_expr=f"({plain_num(c)} IS NULL AND {num(c)} IS NOT NULL)", flag_column=c))
    return issues


def whole_decimals(ctx: Context) -> list[Issue]:
    """Counts like staff or copies stored as 53.0."""
    issues = []
    for c in ctx.columns:
        info = ctx.info[c]
        if info.type != "decimal" or info.n_int == info.nonblank:
            continue
        frac = store.query(f"SELECT count(*) FILTER (WHERE {num(c)} <> floor({num(c)})), "
                           f"count(*) FILTER (WHERE {ident(c)} LIKE '%.%') FROM {ctx.t} WHERE {not_blank(c)}")[0]
        if frac[0] or not frac[1]:
            continue
        issues.append(Issue(
            id=issue_id("format_damage", c, "whole_decimal"), family="format_damage",
            title=f"{c} is whole numbers stored as decimals",
            detail=f"Every {c} value is a whole number written like '53.0'. Shown as counts they read more clearly.",
            severity="format", confidence="certain", columns=[c], affected_rows=frac[1], kind="fix",
            options=[option("Store as whole numbers", {"op": "change_type", "column": c, "to": "integer"})],
            evidence_for=[f"All {n(info.nonblank)} values have no fractional part"],
            flag_expr=f"{ident(c)} LIKE '%.0'", flag_column=c))
    return issues


def text_dates(ctx: Context) -> list[Issue]:
    """Dates written as text in a non-ISO or mixed format, and unix epoch seconds."""
    issues = []
    for c in ctx.columns:
        info = ctx.info[c]
        if info.type == "date":
            iso = store.query(f"SELECT count(*) FILTER (WHERE regexp_matches(trim({ident(c)}), '^\\d{{4}}-\\d{{2}}-\\d{{2}}')) "
                              f"FROM {ctx.t} WHERE {not_blank(c)}")[0][0]
            if iso < 0.95 * info.nonblank:
                issues.append(_date_issue(c, info.nonblank - iso, iso, info.nonblank, ctx))
        elif info.type == "integer" and has_token(c, TIME_TOKENS | {"ts"}) and info.min is not None:
            lo, hi = store.query(f"SELECT min({num(c)}), max({num(c)}) FROM {ctx.t}")[0]
            # 9-10 digit seconds: the only epoch values the "Convert to dates" op understands
            if lo and 1e8 <= lo and hi < 1e10:
                first, last = store.query(f"SELECT strftime(to_timestamp({lit(int(lo))}), '%Y-%m-%d'), "
                                          f"strftime(to_timestamp({lit(int(hi))}), '%Y-%m-%d')")[0]
                issues.append(Issue(
                    id=issue_id("format_damage", c, "epoch"), family="format_damage",
                    title=f"{c} is a computer timestamp, not a readable date",
                    detail=f"Values like {int(lo)} count seconds since 1970. Converting makes them usable as dates.",
                    severity="format", confidence="likely", columns=[c], affected_rows=info.nonblank, kind="fix",
                    options=[option("Convert to dates", {"op": "change_type", "column": c, "to": "date"})],
                    evidence_for=[f"Read as seconds since 1970, the values run from {first} ({int(lo)}) "
                                  f"to {last} ({int(hi)})"]))
    return issues


def _date_issue(col: str, other: int, iso: int, total: int, ctx: Context) -> Issue:
    example = store.query(f"SELECT {ident(col)} FROM {ctx.t} WHERE {not_blank(col)} "
                          f"AND NOT regexp_matches(trim({ident(col)}), '^\\d{{4}}-') LIMIT 1")[0][0]
    mixed = iso > 0
    return Issue(
        id=issue_id("format_damage", col, "date_text"), family="format_damage",
        title=f"{col} mixes date formats" if mixed else f"{col} dates are stored as text ('{example}')",
        detail="Dates like '6/10/2024' are ambiguous (June 10 or October 6?) and sort as text. "
               "Converting stores them one consistent way (YYYY-MM-DD), reading them as month/day.",
        severity="format", confidence="likely", columns=[col], affected_rows=other, kind="fix",
        options=[option("Convert to dates", {"op": "change_type", "column": col, "to": "date"})],
        evidence_for=[f"{n(other)} of {n(total)} values are written like '{example}', not as YYYY-MM-DD"],
        flag_expr=f"NOT regexp_matches(trim({ident(col)}), '^\\d{{4}}-')", flag_column=col)


def combined_field(ctx: Context) -> list[Issue]:
    """Two fields packed into one: 'DevOps-California'."""
    issues = []
    for c in ctx.cols("category", "geo", "text"):
        if c.type != "text" or c.distinct < 4:
            continue
        for sep in SEPARATORS:
            found = _split_stats(ctx, c.name, sep)
            if found:
                issues.append(_combined_issue(ctx, c.name, sep, *found))
                break
    return issues


def _split_stats(ctx: Context, col: str, sep: str):
    """Work on distinct values weighted by their counts, so a 271k-row column costs ~1k values."""
    c, s = "v", lit(sep)
    once = f"(length({c}) - length(replace({c}, {s}, ''))) = {len(sep)}"
    left, right = f"trim(split_part({c}, {s}, 1))", f"trim(split_part({c}, {s}, 2))"
    values = f"(SELECT {ident(col)} AS v, count(*) AS w FROM {ctx.t} WHERE {not_blank(col)} GROUP BY 1)"
    row = store.query(
        f"SELECT sum(w) FILTER (WHERE {once}), count(DISTINCT {left}) FILTER (WHERE {once}), "
        f"count(DISTINCT {right}) FILTER (WHERE {once}), "
        f"count(*) FILTER (WHERE {once} AND (TRY_CAST({left} AS DOUBLE) IS NOT NULL OR TRY_CAST({right} AS DOUBLE) IS NOT NULL)), "
        f"count(*) FILTER (WHERE {once} AND ({left} = '' OR {right} = '')), count(*) FILTER (WHERE {once}) "
        f"FROM {values}")[0]
    with_sep, dl, dr, numeric, empty, distinct_with_sep = row
    total = ctx.info[col].nonblank
    if not with_sep or with_sep < 0.9 * total or not (2 <= dl <= 60 and 2 <= dr <= 100):
        return None
    if numeric > 0.1 * distinct_with_sep or empty:
        return None
    return int(with_sep), dl, dr


def _part_names(col: str, sep: str) -> list[str]:
    parts = [p for p in re.split(r"[_\-\s/|]+", col) if p]
    if len(parts) == 2 and all(p[0].isalpha() for p in parts):
        return parts
    return [f"{col} (part 1)", f"{col} (part 2)"]


def _combined_issue(ctx: Context, col: str, sep: str, count: int, dl: int, dr: int) -> Issue:
    example = ctx.info[col].top_nonblank[0][0] if ctx.info[col].top_nonblank else ""
    into = _part_names(col, sep)
    return Issue(
        id=issue_id("combined_field", col), family="combined_field",
        title=f"{col} packs two fields into one",
        detail=f"Values like '{example}' combine {dl} different first parts with {dr} different second parts. "
               "Split, each can be filtered and grouped on its own.",
        severity="format", confidence="likely", columns=[col], affected_rows=count, kind="fix",
        options=[option(f"Split into {into[0]} and {into[1]}",
                        {"op": "split_column", "column": col, "sep": sep, "into": into})],
        evidence_for=[f"{pct(count, ctx.info[col].nonblank)} of values contain '{sep.strip() or sep}' exactly once",
                      f"{dl} distinct first parts × {dr} distinct second parts"])


def split_id(ctx: Context) -> list[Issue]:
    """One identifier split over two columns: BookID1 + BookID2."""
    issues = []
    for a, b in zip(ctx.columns, ctx.columns[1:]):
        base_a, base_b = re.sub(r"\s*\d+$", "", a), re.sub(r"\s*\d+$", "", b)
        if not base_a or base_a != base_b or a == base_a or not a.endswith("1") or not b.endswith("2"):
            continue
        sample = store.query(f"SELECT {ident(a)}, {ident(b)} FROM {ctx.t} WHERE {not_blank(a)} AND {not_blank(b)} LIMIT 1")
        if not sample:
            continue
        joined = f"{sample[0][0]}{sample[0][1]}"
        evidence = [f"'{sample[0][0]}' + '{sample[0][1]}' → '{joined}'"] + _sibling_match(ctx, a, b, base_a)
        issues.append(Issue(
            id=issue_id("combined_field", a, b), family="combined_field",
            title=f"{base_a} is split across {a} and {b}",
            detail=f"The two halves only mean something together. Combined, {base_a} can be matched to other tables.",
            severity="format", confidence="likely", columns=[a, b], affected_rows=ctx.rows, kind="question",
            question=f"Combine {a} and {b} into one {base_a}?",
            options=[option(f"Combine as '{joined}'", {"op": "combine_columns", "columns": [a, b], "sep": "", "into": base_a}),
                     option(f"Combine as '{sample[0][0]}-{sample[0][1]}'",
                            {"op": "combine_columns", "columns": [a, b], "sep": "-", "into": base_a}),
                     keep_option("Keep them separate")],
            evidence_for=evidence))
    return issues


def _sibling_match(ctx: Context, a: str, b: str, base: str) -> list[str]:
    """Do the combined values exist as a column in another sheet of the same file?"""
    for other in store.DATASETS.values():
        if other.file != ctx.file or other.id == ctx.dataset_id or base not in other.columns:
            continue
        matched = store.query(f"SELECT count(*) FROM {ctx.t} WHERE concat({ident(a)}, {ident(b)}) IN "
                              f"(SELECT {ident(base)} FROM {ident(other.table)})")[0][0]
        if matched:
            return [f"{n(matched)} of {n(ctx.rows)} combined values match {base} in '{other.name}'"]
    return []
