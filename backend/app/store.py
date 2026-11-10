"""In-memory dataset registry and the single shared DuckDB connection."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import duckdb

_con = duckdb.connect(":memory:")
_lock = threading.RLock()


def query(sql: str, params: list[Any] | None = None) -> list[tuple]:
    """Run a query and return all rows. Serialized: DuckDB connections are not thread-safe."""
    with _lock:
        return _con.execute(sql, params or []).fetchall()


def query_with_columns(sql: str, params: list[Any] | None = None) -> tuple[list[str], list[tuple]]:
    with _lock:
        cur = _con.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        return cols, cur.fetchall()


def execute(sql: str, params: list[Any] | None = None) -> None:
    with _lock:
        _con.execute(sql, params or [])


def table_columns(table: str) -> list[str]:
    rows = query("SELECT column_name FROM information_schema.columns WHERE table_name = ? ORDER BY ordinal_position", [table])
    return [r[0] for r in rows]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Decision:
    id: str
    op: dict
    plain: str
    issue_id: str | None
    reason: str | None
    enabled: bool = True
    created_at: str = field(default_factory=now_iso)
    broken: bool = False            # could not be applied (it is then also disabled)
    error: str | None = None

    def to_json(self) -> dict:
        return {
            "id": self.id, "op": self.op, "plain": self.plain, "issue_id": self.issue_id,
            "reason": self.reason, "enabled": self.enabled, "created_at": self.created_at,
            "broken": self.broken, "error": self.error,
        }

    def mark_broken(self, error: str) -> None:
        self.enabled, self.broken, self.error = False, True, error


@dataclass
class DatasetState:
    """Everything Dataful knows about one loaded table."""

    id: str
    name: str
    file: str
    sheet: str | None
    table: str                      # raw, read-only source table (all VARCHAR + __rid)
    rows: int
    columns: list[str]
    demo: bool
    decisions: list[Decision] = field(default_factory=list)
    version: int = 0                # bumped on every decision change
    skipped: set[str] = field(default_factory=set)
    next_decision: int = 1
    # guards decisions, view builds and issue detection for this dataset
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    # caches, keyed by the signature of the enabled decision chain (identical chains share results)
    view_cache: dict[str, Any] = field(default_factory=dict)       # chain signature -> BuiltView
    issues_cache: dict[str, list] = field(default_factory=dict)    # view table -> detected issues
    # AI review results
    ai_orientation: dict | None = None
    ai_issue_text: dict[str, dict] = field(default_factory=dict)
    ai_issues: list = field(default_factory=list)
    # chat with Claude (API messages, append-only) and what the UI shows
    chat_messages: list = field(default_factory=list)
    chat_log: list = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "id": self.id, "name": self.name, "file": self.file, "sheet": self.sheet,
            "rows": self.rows, "columns": len(self.columns), "demo": self.demo,
        }

    def touch(self) -> None:
        self.version += 1

    def new_decision_id(self) -> str:
        decision_id = f"d{self.next_decision}"
        self.next_decision += 1
        return decision_id


DATASETS: dict[str, DatasetState] = {}
_registry_lock = threading.RLock()


def register(ds: DatasetState) -> None:
    with _registry_lock:
        DATASETS[ds.id] = ds


def get(dataset_id: str) -> DatasetState | None:
    return DATASETS.get(dataset_id)


def unique_id(base: str) -> str:
    with _registry_lock:
        if base not in DATASETS:
            return base
        n = 2
        while f"{base}-{n}" in DATASETS:
            n += 1
        return f"{base}-{n}"
