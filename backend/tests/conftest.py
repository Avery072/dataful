"""Shared fixtures: small in-memory datasets and a throwaway data directory for saved decisions."""

from __future__ import annotations

import itertools
import os
import tempfile

import pytest

os.environ.setdefault("DATAFUL_DATA_DIR", tempfile.mkdtemp(prefix="dataful-test-data-"))

from app import loader, persist, store, views  # noqa: E402  (data dir must be set first)

_ids = itertools.count(1)


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """Every test saves decisions into its own empty folder."""
    monkeypatch.setattr(persist, "DATA_DIR", tmp_path / "data")
    return tmp_path / "data"


@pytest.fixture
def make_dataset():
    """make_dataset(csv_text) -> a freshly registered dataset with a unique id."""

    def make(text: str, name: str = "test") -> store.DatasetState:
        return loader.load_csv(text.encode(), f"{name}.csv", dataset_id=f"{name}-{next(_ids)}")

    return make


def view_rows(ds: store.DatasetState, order: str = "__rid") -> tuple[list[str], list[tuple]]:
    """Columns and all rows (without the hidden row id) of the current decision view."""
    view = views.build_view(ds)
    cols = ", ".join(f'"{c}"' for c in view.columns)
    return view.columns, store.query(f'SELECT {cols} FROM "{view.table}" ORDER BY {order}')


EMPLOYEES = "\n".join(
    ["ID,Name,Dept_Region,Amount,Score,Joined,Email,Phone"]
    + [f"E{i},Name{i % 7},{'Sales' if i % 2 else 'Ops'}-{'East' if i % 3 else 'West'},"
       f"\"${1000 + i:,}\",{i}.0,{1 + i % 12}/{1 + i % 27}/2021,user{i % 10}@x.com,-55512340{i:02d}"
       for i in range(30)]
)
