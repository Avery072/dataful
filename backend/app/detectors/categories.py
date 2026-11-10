"""Inconsistent categories: the same label spelled several ways ("Closed Won" / "closed-won" / "Won").

Works on distinct values, never rows, so 271k rows cost the same as their ~1k distinct labels.
Every spelling group in a column becomes ONE issue with one recode mapping (M/m/MALE/male and
F/f/FEMALE/female are one problem: "Gender writes 2 values in 8 ways"). Links, least certain last:
  1. case / whitespace only            -> certain, one-click fix
  2. punctuation, company suffixes,    -> likely, question
     trailing copy numbers ("-1")
  3. fuzzy, or a one-letter abbreviation -> guess, question (raised to likely by a shared ID)
     ("F" for "female"; small columns only)
Targets are always clean (trimmed) and use the capitalisation most rows already use.
"""

from __future__ import annotations

import re
from collections import defaultdict
from statistics import median

from .. import ops, store
from ..sql import ident, lit_list, not_blank
from .base import Context, Issue, count_of, issue_id, n, numeric_like, option, quote_values

MAX_DISTINCT = 5000
FUZZY_MAX_DISTINCT = 50
COMPANY_SUFFIXES = {"inc", "corp", "corporation", "llc", "ltd", "limited", "co", "company", "plc", "gmbh", "ag", "sa"}


def norm_case(v: str) -> str:
    return re.sub(r"\s+", " ", v.strip().lower())


def norm_loose(v: str) -> str:
    tokens = re.sub(r"[^\w\s]|_", " ", norm_case(v)).split()
    while len(tokens) > 1 and tokens[-1] in COMPANY_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _strip_copy_number(key: str, keys: set[str]) -> str:
    """'united states 1' -> 'united states' when that base label also exists."""
    m = re.fullmatch(r"(.+) \d{1,2}", key)
    return m.group(1) if m and m.group(1) in keys else key


def _group(values: dict[str, int], key_fn) -> list[list[str]]:
    buckets: dict[str, list[str]] = defaultdict(list)
    for v in values:
        buckets[key_fn(v)].append(v)
    return [vs for vs in buckets.values() if len(vs) > 1]


def _fuzzy_pairs(reps: list[str]) -> list[tuple[str, str]]:
    """Pairs of loose keys that are near-identical (Jaro-Winkler) or one extends the other by a token."""
    pairs = []
    for a in reps:
        for b in reps:
            if a < b:
                ta, tb = a.split(), b.split()
                short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
                extends = (len(long_) - len(short) == 1 and set(short) <= set(long_)
                           and max(len(t) for t in short) >= 3)
                if extends:
                    pairs.append((a, b))
    rows = store.query("SELECT a, b FROM unnest(?::VARCHAR[]) x(a), unnest(?::VARCHAR[]) y(b) "
                       "WHERE a < b AND left(a, 2) = left(b, 2) AND jaro_winkler_similarity(a, b) >= 0.93",
                       [reps, reps])
    return pairs + [(a, b) for a, b in rows]


def _merge_pairs(groups: dict[str, list[str]], pairs: list[tuple[str, str]]) -> list[list[str]]:
    """Union-find over loose keys; returns groups of original values."""
    parent = {k: k for k in groups}

    def find(k: str) -> str:
        while parent[k] != k:
            k = parent[k]
        return k

    for a, b in pairs:
        parent[find(a)] = find(b)
    merged: dict[str, list[str]] = defaultdict(list)
    for k, vs in groups.items():
        merged[find(k)].extend(vs)
    return [vs for vs in merged.values() if len(vs) > 1]


def inconsistent_categories(ctx: Context) -> list[Issue]:
    issues = []
    for c in ctx.cols("category", "geo", "text"):
        if c.type != "text" or c.distinct < 2 or c.distinct > MAX_DISTINCT or numeric_like(c):
            continue
        rows = store.query(f"SELECT {ident(c.name)}, count(*) FROM {ctx.t} WHERE {not_blank(c.name)} GROUP BY 1")
        counts = {v: k for v, k in rows}
        if median(len(v) for v in counts) > 30:  # free text (comments), not labels
            continue
        issues += _column_issues(ctx, c.name, counts)
    return issues


def _column_issues(ctx: Context, col: str, counts: dict[str, int]) -> list[Issue]:
    """All the spelling groups of one column, as ONE issue with one recode mapping."""
    parent = {v: v for v in counts}
    tiers: dict[str, set[str]] = {v: set() for v in counts}

    def find(v: str) -> str:
        while parent[v] != v:
            v = parent[v]
        return v

    def union(vs: list[str], tier: str) -> None:
        root = find(vs[0])
        tiers[root].add(tier)
        for v in vs[1:]:
            r = find(v)
            if r != root:
                parent[r] = root
                tiers[root] |= tiers.pop(r, set())

    for vs in _group(counts, norm_case):
        union(vs, "case")
    loose_keys = {norm_loose(v) for v in counts}
    bucket_of = {v: _strip_copy_number(norm_loose(v), loose_keys) for v in counts}
    loose: dict[str, list[str]] = defaultdict(list)
    for v, key in bucket_of.items():
        loose[key].append(v)
    for vs in loose.values():
        if len(vs) > 1 and len({norm_case(v) for v in vs}) > 1:
            union(vs, "loose")
    if len(loose) <= FUZZY_MAX_DISTINCT:
        for a, b in _fuzzy_pairs(sorted(loose)):
            union([loose[a][0], loose[b][0]], "fuzzy")
        for short, full in _abbreviations(list(loose)):
            union([loose[short][0], loose[full][0]], "abbr")

    clusters: dict[str, list[str]] = defaultdict(list)
    for v in counts:
        clusters[find(v)].append(v)
    groups = [(tiers.get(root, set()), vs) for root, vs in clusters.items() if len(vs) > 1]
    if not groups:
        return []
    groups.sort(key=lambda g: -sum(counts[v] for v in g[1]))
    style = _house_style([vs for _, vs in groups], counts)
    return [_issue(ctx, col, groups, counts, style)]


def _abbreviations(keys: list[str]) -> list[tuple[str, str]]:
    """'f' -> 'female', 'y' -> 'yes': a single letter that starts exactly one longer label."""
    pairs = []
    for k in keys:
        if len(k) == 1 and k.isalpha():
            longer = [o for o in keys if len(o) >= 3 and o.startswith(k)]
            if len(longer) == 1:
                pairs.append((k, longer[0]))
    return pairs


def _clean(v: str) -> bool:
    return v == v.strip() and "  " not in v


def _style(v: str) -> str:
    return "upper" if v.isupper() else "lower" if v.islower() else "title" if v.istitle() else "mixed"


def _house_style(groups: list[list[str]], counts: dict[str, int]) -> str | None:
    """The capitalisation most rows already use, so every group's target is written the same way."""
    weight: dict[str, int] = defaultdict(int)
    for vs in groups:
        for v in _full_forms(vs):
            if _clean(v):
                weight[_style(v)] += counts[v]
    return max(weight, key=weight.get) if weight else None


def _full_forms(values: list[str]) -> list[str]:
    """The spellings with the longest label (so 'female' wins over 'F').

    Copy numbers don't count towards length, or 'United States-10' would beat 'United States'."""
    def size(v: str) -> int:
        return len(re.sub(r"(?<=\D) \d{1,2}$", "", norm_loose(v)))
    longest = max(size(v) for v in values)
    return [v for v in values if size(v) == longest]


def _target(values: list[str], counts: dict[str, int], style: str | None) -> str:
    """Never a messy spelling: trimmed, in the column's usual capitalisation, then the most common."""
    pool = [v for v in _full_forms(values) if _clean(v)] or [v for v in values if _clean(v)]
    if not pool:
        return re.sub(r"\s+", " ", max(values, key=lambda v: counts[v]).strip())
    styled = [v for v in pool if _style(v) == style] or pool
    return sorted(styled, key=lambda v: (-counts[v], v))[0]


TIER_EVIDENCE = {
    "case": "Some differ only in capital letters or spacing",
    "loose": "Some match once punctuation, suffixes like Inc/Corp, or copy numbers are ignored",
    "fuzzy": "Some spellings are very similar",
    "abbr": "Some look like one-letter abbreviations ('F' for 'female')",
}


def _issue(ctx: Context, col: str, groups: list[tuple[set[str], list[str]]], counts: dict[str, int],
           style: str | None) -> Issue:
    mapping: dict[str, str] = {}
    tidy: dict[str, str] = {}          # capitals/spacing only
    targets = []
    for _, vs in groups:
        target = _target(vs, counts, style)
        targets.append(target)
        for v in vs:
            if v != target:
                mapping[v] = target
        for same in _group({v: counts[v] for v in vs}, norm_case):
            t = _target(same, counts, style)
            tidy.update({v: t for v in same if v != t})
    if len(mapping) > ops.MAX_RECODE:   # keep the biggest groups
        mapping = dict(sorted(mapping.items(), key=lambda kv: -counts[kv[0]])[:ops.MAX_RECODE])
    tiers = set().union(*(t for t, _ in groups))
    affected = sum(counts[v] for v in mapping)
    variants = sum(len(vs) for _, vs in groups)
    confidence = ("certain" if tiers == {"case"} else "likely" if tiers <= {"case", "loose", "abbr"} else "guess")
    support, against = [], []
    for _, vs in groups[:5]:
        s, a = _id_evidence(ctx, col, vs)
        support += s
        against += a
    if support and confidence == "guess":
        confidence = "likely"
    if against and confidence != "certain":
        confidence = "guess"
    shown = "; ".join(f"{quote_values(sorted(vs, key=lambda v: -counts[v]), 4)} → '{t}'"
                      for (_, vs), t in zip(groups[:3], targets[:3]))
    more = f" (+{len(groups) - 3} more groups)" if len(groups) > 3 else ""
    title = (f"{col} writes {count_of(len(groups), 'value')} in {n(variants)} ways" if len(groups) > 1
             else f"{col} writes '{targets[0]}' in {n(variants)} ways")
    evidence_for = [TIER_EVIDENCE[t] for t in ("case", "loose", "fuzzy", "abbr") if t in tiers]
    evidence_for += [f"'{v}' appears {count_of(counts[v], 'time')}"
                     for v in sorted(groups[0][1], key=lambda v: -counts[v])[:4]]
    common = dict(
        id=issue_id("inconsistent_categories", col, "_".join(sorted(tiers))),
        family="inconsistent_categories", title=title, severity="numbers", confidence=confidence,
        columns=[col], affected_rows=affected, evidence_for=evidence_for + support[:3], evidence_against=against[:3],
        flag_expr=f"{ident(col)} IN {lit_list(list(mapping))}", flag_column=col,
        meta={"groups": [vs for _, vs in groups], "targets": targets})
    recode = {"op": "recode_values", "column": col, "mapping": mapping}
    use = f"Use {quote_values(targets, 4)}"
    if tiers == {"case"}:
        return Issue(**common, kind="fix", detail=f"{shown}{more}. Group-by splits each one into several rows.",
                     options=[option(use, recode)])
    options = [option(f"Yes, {use[0].lower()}{use[1:]}", recode)]
    if tidy and tidy != mapping:
        options.append(option("Only fix capitals and spaces",
                              {"op": "recode_values", "column": col, "mapping": tidy}))
    unsure = sorted({v for t, vs in groups if t - {"case"} for v in vs}, key=lambda v: -counts[v])
    options.append(option("No, they're different", {"op": "keep_separate", "column": col, "values": unsure[:50]}))
    return Issue(**common, kind="question",
                 detail=f"{shown}{more}. If these are the same, totals are split across several labels.",
                 question=f"Do these spellings in {col} mean the same thing?", options=options)


def _id_evidence(ctx: Context, col: str, values: list[str]) -> tuple[list[str], list[str]]:
    """Do the variants share one value of an ID column (strong) or map to different IDs (conflict)?"""
    support, against = [], []
    for idc in ctx.cols("identifier"):
        if idc.name == col:
            continue
        rows = store.query(f"SELECT {ident(col)}, list(DISTINCT {ident(idc.name)}) FROM {ctx.t} "
                           f"WHERE {ident(col)} IN {lit_list(values)} AND {not_blank(idc.name)} GROUP BY 1")
        if len(rows) < 2:
            continue
        sets = [set(ids) for _, ids in rows]
        if all(len(s) == 1 for s in sets) and len(set.union(*sets)) == 1:
            support.append(f"All share {idc.name} '{next(iter(sets[0]))}'")
        elif not set.intersection(*sets) and all(len(s) <= 3 for s in sets):
            against.append(f"They have different {idc.name} values")
    return support, against
