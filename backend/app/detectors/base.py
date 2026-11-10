"""Shared types and helpers for the issue detectors."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .. import store
from ..profile import ColumnInfo, has_token, name_tokens
from ..sql import ident

SEVERITY_ORDER = {"numbers": 0, "missing": 1, "format": 2}
CONFIDENCE_ORDER = {"certain": 0, "likely": 1, "guess": 2}
MAX_FLAG_RIDS = 200_000

MONEY_TOKENS = {"amount", "revenue", "sales", "price", "value", "total", "cost", "spend", "budget", "fee",
                "arr", "mrr", "income", "payment", "deal", "subtotal"}
PERSON_NAME_TOKENS = {"name", "first", "last", "surname", "firstname", "lastname", "fullname"}


@dataclass
class Issue:
    """One detected problem. Internal flag fields say which cells to highlight in the grid."""

    id: str
    family: str
    title: str
    detail: str
    severity: str
    confidence: str
    columns: list[str]
    affected_rows: int
    kind: str                                   # "fix" | "question"
    options: list[dict]
    question: str | None = None
    evidence_for: list[str] = field(default_factory=list)
    evidence_against: list[str] = field(default_factory=list)
    source: str = "rules"
    flag_expr: str | None = None                # SQL boolean over a row (cell-level highlight)
    flag_rids: frozenset[int] | None = None     # explicit row ids (row-level highlight)
    flag_column: str | None = None
    meta: dict = field(default_factory=dict)    # detector facts reused elsewhere (e.g. orientation)

    def sort_key(self) -> tuple:
        return (SEVERITY_ORDER[self.severity], CONFIDENCE_ORDER[self.confidence], -self.affected_rows)

    def to_json(self, status: str = "open", decision_id: str | None = None) -> dict:
        return {
            "id": self.id, "family": self.family, "title": self.title, "detail": self.detail,
            "severity": self.severity, "confidence": self.confidence, "columns": self.columns,
            "affected_rows": self.affected_rows,
            "evidence": {"for": self.evidence_for, "against": self.evidence_against},
            "kind": self.kind, "question": self.question, "options": self.options,
            "status": status, "decision_id": decision_id, "source": self.source,
        }


@dataclass
class Context:
    """What a detector needs: the table and per-column statistics."""

    dataset_id: str
    file: str
    table: str
    rows: int
    columns: list[str]
    info: dict[str, ColumnInfo]

    @property
    def t(self) -> str:
        return ident(self.table)

    def cols(self, *roles: str) -> list[ColumnInfo]:
        return [self.info[c] for c in self.columns if self.info[c].role in roles]

    def unique_id_column(self) -> ColumnInfo | None:
        """A column that identifies each row (ID-like name, every value distinct)."""
        for c in self.cols("identifier"):
            if c.nonblank == self.rows and c.distinct == self.rows:
                return c
        return None

    def rids(self, sql: str) -> frozenset[int]:
        """Run a query returning row ids (first column) and cap the result size."""
        return frozenset(r[0] for r in store.query(f"{sql} LIMIT {MAX_FLAG_RIDS}"))


def issue_id(family: str, *parts: str) -> str:
    slug = "-".join(re.sub(r"[^a-z0-9]+", "_", p.lower()).strip("_") for p in parts if p)
    return f"{family}:{slug}" if slug else family


def option(label: str, op: dict | None, description: str | None = None) -> dict:
    out: dict = {"label": label, "op": op}
    if description:
        out["description"] = description
    return out


def keep_option(label: str = "Keep as is", description: str | None = None) -> dict:
    return option(label, None, description)


def n(value: int) -> str:
    return f"{value:,}"


def count_of(value: int, word: str, plural_form: str | None = None) -> str:
    """'1 row', '1,385 rows'."""
    return f"{n(value)} {word if value == 1 else plural_form or plural(word)}"


def are(value: int) -> str:
    return "is" if value == 1 else "are"


def a_an(word: str) -> str:
    """'an Email', 'a Phone' (by first letter; good enough for column names)."""
    return ("an " if word[:1].lower() in "aeiou" else "a ") + word


def pct(part: int, whole: int) -> str:
    if not whole:
        return "0%"
    p = 100 * part / whole
    return f"{p:.0f}%" if p >= 1 else f"{p:.1f}%"


def quote_values(values: list, limit: int = 3) -> str:
    shown = ", ".join(f"'{v}'" for v in values[:limit])
    return shown + (f" (+{len(values) - limit} more)" if len(values) > limit else "")


def noun(column: str) -> str:
    """'Deal ID' -> 'deal', 'Employee_ID' -> 'employee'; falls back to the column name."""
    words = [t for t in name_tokens(column) if t not in {"id", "key", "code", "no", "num", "number"}]
    return " ".join(words) or column


def entity_noun(column: str, file: str) -> str:
    """Noun for what an ID column identifies; a bare 'ID' falls back to the file name ('athlete_events')."""
    word = noun(column)
    if word != column:
        return word
    tokens = name_tokens(re.sub(r"\.\w+$", "", file))
    return tokens[0] if len(tokens) > 1 else "record"


def plural(word: str) -> str:
    if word.endswith("s"):
        return word
    if word.endswith("y") and not word.endswith(("ay", "ey", "oy", "uy")):
        return word[:-1] + "ies"
    return word + "s"


def is_money(c: ColumnInfo) -> bool:
    return has_token(c.name, MONEY_TOKENS)


def numeric_like(c: ColumnInfo) -> bool:
    """Numeric, or text that becomes numeric once '$' and ',' are removed."""
    return c.nonblank > 0 and c.n_num_clean >= 0.9 * c.nonblank


def ordered(issues: list[Issue]) -> list[Issue]:
    return sorted(issues, key=Issue.sort_key)

