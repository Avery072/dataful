"""The three kinds of duplicates: copied rows, the same record twice, and double counting.

Plus fake unique IDs (an ID-looking column that does not identify anything).
Nothing here ever merges automatically: copies are a one-click fix, everything else is a question.
"""

from __future__ import annotations

from itertools import combinations
from statistics import median

from .. import store
from ..ops import join_names
from ..profile import has_token
from ..sql import ROW_ID, ident, lit, not_blank, num
from .base import (
    PERSON_NAME_TOKENS,
    Context,
    Issue,
    a_an,
    are,
    count_of,
    entity_noun,
    is_money,
    issue_id,
    keep_option,
    n,
    noun,
    numeric_like,
    option,
    pct,
    plural,
    quote_values,
)

IDENTITY_TOKENS = {"age", "birth", "birthday", "dob", "born", "sex", "gender", "department", "dept",
                   "city", "state", "country", "region", "company", "account"}
CONTACT_TOKENS = {"email", "mail", "phone", "tel", "mobile"}


def _group_cols(cols: list[str]) -> str:
    return ", ".join(ident(c) for c in cols)


def _all_not_blank(cols: list[str]) -> str:
    return " AND ".join(not_blank(c) for c in cols)


# ---------- copied rows ----------

def duplicate_rows(ctx: Context) -> list[Issue]:
    issues = []
    exact = _copies(ctx, ctx.columns)
    if exact:
        groups, extra, rids, example = exact
        issues.append(Issue(
            id=issue_id("duplicate_rows", "all"), family="duplicate_rows",
            title=f"{count_of(extra, 'row')} {are(extra)} exact copies",
            detail="These rows repeat another row in every column, so every count and total that includes them is inflated.",
            severity="numbers", confidence="certain", columns=list(ctx.columns), affected_rows=extra,
            kind="fix", options=[option("Keep one copy of each", {"op": "remove_duplicates", "columns": None})],
            evidence_for=[f"{count_of(groups, 'group')} of identical rows", example],
            evidence_against=["Two genuinely identical events would also look like this (rare)."],
            flag_rids=rids, flag_column=ctx.columns[0]))
    uid = ctx.unique_id_column()
    if uid:
        others = [c for c in ctx.columns if c != uid.name]
        near = _copies(ctx, others) if len(others) >= 2 else None
        if near and (not exact or near[1] > exact[1]):
            groups, extra, rids, example = near
            issues.append(Issue(
                id=issue_id("duplicate_rows", "except", uid.name), family="duplicate_rows",
                title=f"{count_of(extra, 'row')} {are(extra)} identical except for {uid.name}",
                detail=f"Every field matches another row; only the {uid.name} differs. Often the same record exported twice with a new ID.",
                severity="numbers", confidence="guess", columns=others, affected_rows=extra, kind="question",
                question=f"Are rows that differ only in {uid.name} the same record?",
                options=[option("Yes, keep one", {"op": "remove_duplicates", "columns": others}),
                         option("Flag them for review", {"op": "flag_duplicates", "key": others, "label": "Possible duplicate"}),
                         keep_option("No, they are different")],
                evidence_for=[f"{n(groups)} groups match in all {len(others)} other columns", example],
                evidence_against=[f"Each row has its own {uid.name}; they may be two genuine, identical events."],
                flag_rids=rids, flag_column=others[0]))
    return issues


def _copies(ctx: Context, cols: list[str]):
    """(groups, extra copies, row ids of the extra copies, example) or None."""
    g = _group_cols(cols)
    row = store.query(f"SELECT count(*), sum(c - 1) FROM (SELECT count(*) c FROM {ctx.t} GROUP BY {g} HAVING c > 1)")[0]
    if not row[0]:
        return None
    rids = ctx.rids(f"SELECT {ROW_ID} FROM {ctx.t} QUALIFY row_number() OVER (PARTITION BY {g} ORDER BY {ROW_ID}) > 1")
    ex = store.query(f"SELECT min({ROW_ID}), max({ROW_ID}), count(*) c FROM {ctx.t} GROUP BY {g} HAVING c > 1 "
                     f"ORDER BY c DESC LIMIT 1")[0]
    example = f"For example rows {n(ex[0])} and {n(ex[1])} are identical ({ex[2]} copies in that group)."
    return row[0], int(row[1]), rids, example


# ---------- the same record twice ----------

def duplicate_records(ctx: Context) -> list[Issue]:
    """People/companies entered twice under different IDs (matching on name + identity fields)."""
    uid = ctx.unique_id_column()
    if not uid:
        return []
    names = [c.name for c in ctx.cols("text", "category") if has_token(c.name, PERSON_NAME_TOKENS)]
    if not names:
        return []
    identity = [c for c in ctx.columns if c not in names and c != uid.name and has_token(c, IDENTITY_TOKENS)
                and ctx.info[c].role != "identifier"]
    key = names + identity
    g, where = _group_cols(key), _all_not_blank(key)
    groups = store.query(f"SELECT count(*), sum(c) FROM (SELECT count(*) c FROM {ctx.t} WHERE {where} "
                         f"GROUP BY {g} HAVING c > 1 AND count(DISTINCT {ident(uid.name)}) > 1)")[0]
    if not groups[0]:
        return []
    group_count, rows_in = groups[0], int(groups[1])
    example = store.query(f"SELECT {g}, list({ident(uid.name)} ORDER BY {ROW_ID}) ids FROM {ctx.t} WHERE {where} "
                          f"GROUP BY {g} HAVING count(*) > 1 ORDER BY count(*) DESC LIMIT 1")[0]
    shared = ", ".join(f"{k} '{v}'" for k, v in zip(key, example[:-1]))
    agree, conflict = _agree_conflict(ctx, key, uid.name)
    strong = [c for c in agree if has_token(c, CONTACT_TOKENS) and ctx.info[c].unique_ratio >= 0.9]
    confidence = "likely" if strong else "guess"
    options = [option("Flag them as possible duplicates", {"op": "flag_duplicates", "key": key, "label": "Possible duplicate"}),
               option("They're different people", {"op": "keep_separate", "column": names[0],
                                                    "values": [str(example[0])]})]
    if strong:
        options.insert(1, option("Merge them (keep the first)", {"op": "merge_records", "key": key, "keep": "first"}))
    rids = ctx.rids(f"SELECT {ROW_ID} FROM {ctx.t} WHERE {where} QUALIFY count(*) OVER (PARTITION BY {g}) > 1")
    return [Issue(
        id=issue_id("duplicate_records", *key), family="duplicate_records",
        title=f"{count_of(rows_in, 'row')} may be the same {noun(uid.name)} entered twice",
        detail=f"{count_of(group_count, 'group')} of rows share the same {join_names(key)} but have different "
               f"{plural(uid.name)}. They could be duplicates, or just people who happen to match.",
        severity="numbers", confidence=confidence, columns=key, affected_rows=rows_in, kind="question",
        question=f"Are rows with the same {join_names(key)} the same {noun(uid.name)}?",
        options=options,
        evidence_for=[f"Example: {shared} → {plural(uid.name)} {quote_values(example[-1])}"]
                     + [f"They also share {c}" for c in agree[:3]],
        evidence_against=[f"Each row has a different {uid.name}"] + [f"{c} differs in {p} of groups" for c, p in conflict[:3]],
        flag_rids=rids, flag_column=key[0])]


def _agree_conflict(ctx: Context, key: list[str], uid: str) -> tuple[list[str], list[tuple[str, str]]]:
    """Columns that agree within every matching group vs. columns that usually differ."""
    others = [c for c in ctx.columns if c not in key and c != uid]
    if not others:
        return [], []
    g, where = _group_cols(key), _all_not_blank(key)
    aggs = ", ".join(f"count(*) FILTER (WHERE d{i} > 1)" for i in range(len(others)))
    inner = ", ".join(f"count(DISTINCT {ident(c)}) d{i}" for i, c in enumerate(others))
    row = store.query(f"SELECT count(*), {aggs} FROM (SELECT {inner} FROM {ctx.t} WHERE {where} "
                      f"GROUP BY {g} HAVING count(*) > 1)")[0]
    total = row[0] or 1
    agree = [c for c, d in zip(others, row[1:]) if d == 0]
    conflict = sorted(((c, d) for c, d in zip(others, row[1:]) if d / total >= 0.5), key=lambda x: -x[1])
    return agree, [(c, pct(d, total)) for c, d in conflict]


# ---------- double counting ----------

def double_counting(ctx: Context) -> list[Issue]:
    return _repeated_key(ctx) + _shared_outcome(ctx)


def _repeated_key(ctx: Context) -> list[Issue]:
    """A record (deal, order) repeated once per child row (contact, line) with the same amount."""
    measures = [c for c in ctx.columns if is_money(ctx.info[c]) and numeric_like(ctx.info[c])
                and ctx.info[c].role != "identifier"]
    keys = [c for c in ctx.cols("identifier") if not has_token(c.name, {"email", "mail", "phone", "tel", "mobile"})
            and 0.3 <= c.unique_ratio < 0.98 and c.nonblank >= 20]
    issues = []
    for key in keys:
        for m in measures:
            issue = _repeated_key_issue(ctx, key.name, m)
            if issue:
                issues.append(issue)
                break
    return issues


def _repeated_key_issue(ctx: Context, key: str, measure: str) -> Issue | None:
    others = [c for c in ctx.columns if c not in (key, measure)]
    row_sig = "concat_ws(chr(31), " + ", ".join(f"coalesce({ident(c)}, '')" for c in others) + ")"
    k = ident(key)
    stats = store.query(
        f"SELECT count(*), count(*) FILTER (WHERE c > 1), count(*) FILTER (WHERE c > 1 AND dm = 1 AND ds > 1), "
        f"sum(c) FILTER (WHERE c > 1 AND dm = 1 AND ds > 1) "
        f"FROM (SELECT count(*) c, count(DISTINCT {ident(measure)}) dm, count(DISTINCT {row_sig}) ds "
        f"FROM {ctx.t} WHERE {not_blank(key)} GROUP BY {k})")[0]
    keys_total, repeated, same_measure, rows_in = stats
    if repeated < 5 or same_measure < 0.8 * repeated or repeated < 0.01 * keys_total:
        return None
    m = num(measure)
    naive, once = store.query(
        f"SELECT (SELECT sum({m}) FROM {ctx.t}), "
        f"(SELECT sum(v) FROM (SELECT any_value({m}) v FROM {ctx.t} WHERE {not_blank(key)} GROUP BY {k})) "
        f"+ coalesce((SELECT sum({m}) FROM {ctx.t} WHERE NOT {not_blank(key)}), 0)")[0]
    varying = _varying_columns(ctx, key, others)
    ex = store.query(f"SELECT {k}, count(*) c, any_value({ident(measure)}) FROM {ctx.t} WHERE {not_blank(key)} "
                     f"GROUP BY {k} HAVING count(DISTINCT {ident(measure)}) = 1 ORDER BY c DESC LIMIT 1")[0]
    thing = noun(key)
    rows_in = int(rows_in)
    rids = ctx.rids(f"SELECT {ROW_ID} FROM {ctx.t} WHERE {not_blank(key)} "
                    f"QUALIFY row_number() OVER (PARTITION BY {k} ORDER BY {ROW_ID}) > 1")
    per = f" (one row per {join_names(varying[:2])})" if varying else ""
    return Issue(
        id=issue_id("double_counting", key, measure), family="double_counting",
        title=f"{count_of(same_measure, thing)} appear on {n(rows_in)} rows{per}",
        detail=f"Each of these {plural(thing)} repeats the same {measure} on every one of its rows, so adding up "
               f"{measure} counts them {n(rows_in - same_measure)} extra times.",
        severity="numbers", confidence="likely", columns=[key, measure], affected_rows=rows_in,
        kind="question", question=f"Should each {thing} be counted once?",
        options=[option(f"Count each {thing} once", {"op": "set_count_unit", "columns": [key], "label": plural(thing)},
                        "Totals and counts use one row per " + thing + "; no rows are removed."),
                 option(f"Keep one row per {thing}", {"op": "merge_records", "key": [key], "keep": "first"},
                        "Removes the repeated rows (and the extra " + (varying[0] if varying else "details") + ")."),
                 keep_option("Each row is separate")],
        evidence_for=[f"{key} {ex[0]} appears on {ex[1]} rows, each with {measure} {ex[2]}",
                      f"Sum of {measure}: {_money(naive)} adding every row vs {_money(once)} counting each {thing} once"],
        evidence_against=[f"{join_names(varying[:3])} differ between the repeated rows"] if varying else [],
        flag_rids=rids, flag_column=key, meta={"key": key, "varying": varying})


def _varying_columns(ctx: Context, key: str, others: list[str]) -> list[str]:
    inner = ", ".join(f"count(DISTINCT {ident(c)}) > 1 AS v{i}" for i, c in enumerate(others))
    aggs = ", ".join(f"count(*) FILTER (WHERE v{i})" for i in range(len(others)))
    row = store.query(f"SELECT count(*), {aggs} FROM (SELECT {inner} FROM {ctx.t} WHERE {not_blank(key)} "
                      f"GROUP BY {ident(key)} HAVING count(*) > 1)")[0]
    return [c for c, v in zip(others, row[1:]) if row[0] and v >= 0.5 * row[0]]


def _money(v) -> str:
    return "—" if v is None else f"{v:,.0f}"


def _shared_outcome(ctx: Context) -> list[Issue]:
    """One outcome (a team medal, a shared prize) copied onto every participant's row."""
    entity = next((c for c in ctx.cols("identifier") if c.unique_ratio < 1), None)
    if not entity:
        return []
    # an "outcome" is sparse: most participants have none (no medal), a few share one
    outcomes = [c for c in ctx.cols("category") if 2 <= c.distinct <= 8 and c.nonblank >= 50 and c.missing_pct >= 0.3]
    context = sorted((c for c in ctx.cols("category", "time", "geo")
                      if 10 <= c.distinct <= 0.5 * ctx.rows and c.missing_pct < 0.2),
                     key=lambda c: -c.distinct)[:6]
    for outcome in outcomes:
        found = _best_context(ctx, entity.name, outcome.name, [c.name for c in context if c.name != outcome.name])
        if found:
            side = _side_columns(ctx, entity.name, outcome.name, found[0])
            keys = found[0] + side
            return [_shared_outcome_issue(ctx, entity.name, outcome.name, keys, *_unit_counts(ctx, outcome.name, keys),
                                          side=side)]
    return []


def _side_columns(ctx: Context, entity: str, outcome: str, keys: list[str]) -> list[str]:
    """A column naming whose side a shared outcome belongs to (a country, a team), so a tie between rivals
    (two bronzes in one judo event) isn't mistaken for one shared medal.

    It must be the same for nearly everyone sharing an outcome, and where it differs, every participant must
    differ (a tie between individuals), not just some (a mixed team, e.g. Sex in mixed doubles)."""
    g = _group_cols(keys + [outcome])
    best = None
    for c in ctx.cols("category", "geo", "text", "identifier"):
        if c.name in (entity, outcome, *keys) or not 2 <= c.distinct <= 0.5 * ctx.rows:
            continue
        shared, same, ties = store.query(
            f"SELECT count(*), count(*) FILTER (WHERE d = 1), count(*) FILTER (WHERE d > 1 AND d = e) FROM ("
            f"SELECT count(DISTINCT {ident(c.name)}) d, count(DISTINCT {ident(entity)}) e FROM {ctx.t} "
            f"WHERE {not_blank(outcome)} GROUP BY {g} HAVING count(DISTINCT {ident(entity)}) > 1)")[0]
        split = shared - same
        if shared and split and same / shared >= 0.8 and ties / split >= 0.8:
            score = (round(ties / split, 2), -c.distinct)   # near-equal: fewer distinct values (NOC over Team)
            if best is None or score > best[0]:
                best = (score, c.name)
    return [best[1]] if best else []


def _unit_counts(ctx: Context, outcome: str, keys: list[str]) -> tuple[int, int, int]:
    """Rows with an outcome, distinct outcomes, and rows whose outcome is shared, under these keys."""
    g = _group_cols(keys + [outcome])
    rows = store.query(f"SELECT count(*), count(*) > 1 FROM {ctx.t} WHERE {not_blank(outcome)} GROUP BY {g}")
    return sum(c for c, _ in rows), len(rows), sum(c for c, m in rows if m)


def _best_context(ctx: Context, entity: str, outcome: str, candidates: list[str]):
    """Smallest set of event columns where the outcome is usually unique but sometimes shared."""
    for size in (1, 2):
        accepted = []
        for keys in combinations(candidates, size):
            g = _group_cols(list(keys) + [outcome])
            rows = store.query(f"SELECT c, e FROM (SELECT count(*) c, count(DISTINCT {ident(entity)}) e FROM {ctx.t} "
                               f"WHERE {not_blank(outcome)} GROUP BY {g})")
            if len(rows) < 20 or median(c for c, _ in rows) != 1:
                continue
            multi = [c for c, e in rows if e > 1]
            total = sum(c for c, _ in rows)
            share = sum(multi) / total
            if share >= 0.1 and sum(multi) / len(multi) >= 2.5:
                accepted.append((share, -len(rows), list(keys), total, len(rows), sum(multi)))
        if accepted:
            share, _, keys, total, units, multi_rows = min(accepted)
            return keys, total, units, multi_rows
    return None


def _shared_outcome_issue(ctx: Context, entity: str, outcome: str, keys: list[str], total: int, units: int,
                          multi_rows: int, side: list[str] = ()) -> Issue:
    unit_cols = keys + [outcome]
    g = _group_cols(unit_cols)
    ex = store.query(f"SELECT {g}, count(*) c FROM {ctx.t} WHERE {not_blank(outcome)} GROUP BY {g} "
                     f"ORDER BY c DESC LIMIT 1")[0]
    label = plural(outcome.lower())
    thing = outcome.lower()
    who = entity_noun(entity, ctx.file)
    evidence = [f"{n(total)} rows have {a_an(outcome)}, but they hold only {n(units)} distinct {label}",
                f"{' · '.join(str(v) for v in ex[:-1])}: one {thing} copied onto {ex[-1]} rows, one per {who}"]
    evidence += _example_by_geo(ctx, outcome, unit_cols, label, side)
    rids = ctx.rids(f"SELECT {ROW_ID} FROM {ctx.t} WHERE {not_blank(outcome)} "
                    f"QUALIFY count(*) OVER (PARTITION BY {g}) > 1")
    return Issue(
        id=issue_id("double_counting", *unit_cols), family="double_counting",
        title=f"Shared {label} are counted once per {who}",
        detail=f"When several {plural(who)} share one {thing} (a team result), it is copied onto each of their rows. "
               f"Counting rows gives {n(total)} {label}; counting each shared {thing} once gives {n(units)}.",
        severity="numbers", confidence="likely", columns=unit_cols, affected_rows=multi_rows, kind="question",
        question=f"Should a shared {thing} count once, or once per {who}?",
        options=[option(f"Count a shared {thing} once", {"op": "set_count_unit", "columns": unit_cols, "label": label},
                        f"A {thing} won together by several {plural(who)} counts as one {thing}. Rows are unchanged."),
                 keep_option(f"Once per {who}", f"Keep counting every row (each {who}'s own {thing}).")],
        evidence_for=evidence,
        evidence_against=[f"{pct(total - multi_rows, total)} of rows with {a_an(outcome)} are not shared (individual results)"],
        flag_rids=rids, flag_column=outcome, meta={"entity": entity, "keys": keys})


def _example_by_geo(ctx: Context, outcome: str, unit_cols: list[str], label: str, side=()) -> list[str]:
    """'USA, Gold: 2,638 rows but only 1,131 distinct medals' — the number a user would quote."""
    candidates = ctx.cols("geo") + ctx.cols("category")
    geo = next((c.name for c in candidates if (c.name in side or c.name not in unit_cols) and c.distinct >= 5), None)
    if not geo:
        return []
    top_outcome = store.query(f"SELECT {ident(outcome)} FROM {ctx.t} WHERE {not_blank(outcome)} "
                              f"GROUP BY 1 ORDER BY count(*) DESC LIMIT 1")[0][0]
    key = "concat_ws(chr(31), " + ", ".join(ident(c) for c in unit_cols) + ")"
    row = store.query(f"SELECT {ident(geo)}, count(*) c, count(DISTINCT {key}) FROM {ctx.t} "
                      f"WHERE {ident(outcome)} = {lit(top_outcome)} GROUP BY 1 ORDER BY c DESC LIMIT 1")
    if not row:
        return []
    g, rows, distinct = row[0]
    return [f"{g}, {top_outcome}: {n(rows)} rows but only {n(distinct)} distinct {label}"]


# ---------- fake unique IDs ----------

def fake_unique_id(ctx: Context, skip: set[str] | None = None) -> list[Issue]:
    """A personal identifier (email, phone) that repeats across rows that each have their own ID.

    Reference IDs (BookID in a ratings table) repeat by design, so only contact-style keys count.
    """
    uid = ctx.unique_id_column()
    if not uid:
        return []
    issues = []
    for c in ctx.cols("identifier"):
        if c is uid or (skip and c.name in skip) or not (0 < c.unique_ratio < 0.9) or c.nonblank < 20:
            continue
        if not has_token(c.name, CONTACT_TOKENS | {"ssn", "username", "login"}):
            continue
        k = ident(c.name)
        groups = store.query(f"SELECT count(*), sum(n) FROM (SELECT count(*) n FROM {ctx.t} "
                             f"WHERE {not_blank(c.name)} GROUP BY {k} HAVING n > 1)")[0]
        if not groups[0]:
            continue
        ex = store.query(f"SELECT {k}, count(*) d FROM {ctx.t} WHERE {not_blank(c.name)} "
                         f"GROUP BY {k} ORDER BY d DESC LIMIT 1")[0]
        issues.append(Issue(
            id=issue_id("fake_unique_id", c.name), family="fake_unique_id",
            title=f"{c.name} looks like an ID but is shared by different records",
            detail=f"Only {n(c.distinct)} distinct {c.name} values for {n(c.nonblank)} rows that each have their own "
                   f"{uid.name}. Matching or counting by {c.name} would lump different records together.",
            severity="numbers", confidence="likely", columns=[c.name], affected_rows=int(groups[1]), kind="question",
            question=f"Can {c.name} be used to tell records apart?",
            options=[option(f"No — flag rows that share {a_an(c.name)}", {"op": "flag_duplicates", "key": [c.name],
                                                                    "label": f"Shared {c.name}"}),
                     keep_option("Yes, it's fine")],
            evidence_for=[f"'{ex[0]}' is used by {ex[1]} different {plural(uid.name)}",
                          f"{count_of(groups[0], c.name + ' value')} appear{'s' if groups[0] == 1 else ''} on more than one row"],
            evidence_against=[f"{pct(c.distinct, c.nonblank)} of values are distinct"],
            flag_column=c.name,
            flag_rids=ctx.rids(f"SELECT {ROW_ID} FROM {ctx.t} WHERE {not_blank(c.name)} "
                               f"QUALIFY count(*) OVER (PARTITION BY {k}) > 1")))
    return issues
