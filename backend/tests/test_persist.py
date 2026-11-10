"""Decisions survive a restart; bad saved state never makes a dataset unloadable."""

from __future__ import annotations

import json

from conftest import EMPLOYEES

from app import issues, persist, service, store, views


def fresh_copy(ds: store.DatasetState) -> store.DatasetState:
    """What startup does: a new in-memory state for the same table, then load the saved file."""
    copy = store.DatasetState(id=ds.id, name=ds.name, file=ds.file, sheet=None, table=ds.table,
                              rows=ds.rows, columns=list(ds.columns), demo=False)
    persist.load(copy)
    return copy


def test_round_trip(make_dataset, data_dir):
    ds = make_dataset(EMPLOYEES, "persist")
    first = service.add_decision(ds, {"op": "mark_missing", "column": "Name", "values": ["Name1"]}, None, "why")
    second = service.add_decision(ds, None, "fake_unique_id:email", "Yes")
    service.set_enabled(ds, first, False)
    issue = issues.find(ds, "combined_field:dept_region")
    service.skip_issue(ds, issue)
    assert (data_dir / "decisions" / f"{ds.id}.json").exists()

    copy = fresh_copy(ds)
    assert [d.to_json() for d in copy.decisions] == [first.to_json(), second.to_json()]
    assert copy.skipped == {"combined_field:dept_region"}
    assert service.add_decision(copy, None, "combined_field:dept_region", None).id not in {first.id, second.id}


def test_broken_decision_is_disabled_not_fatal(make_dataset, data_dir):
    ds = make_dataset(EMPLOYEES, "broken")
    path = data_dir / "decisions" / f"{ds.id}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"decisions": [
        {"id": "d1", "op": {"op": "mark_missing", "column": "Gone", "values": ["x"]}, "enabled": True},
        {"id": "d2", "op": "not an op", "enabled": True},
        {"id": "d3", "op": {"op": "mark_missing", "column": "Name", "values": ["Name1"]}, "enabled": True},
        "junk",
    ]}))
    copy = fresh_copy(ds)
    view = views.build_view(copy)
    states = {d.id: (d.enabled, d.broken) for d in copy.decisions}
    assert states == {"d1": (False, True), "d2": (False, True), "d3": (True, False)}
    assert view.table != ds.table   # d3 still applies
    saved = json.loads(path.read_text())["decisions"]
    assert [d["broken"] for d in saved] == [True, True, False]


def test_corrupted_file_is_set_aside(make_dataset, data_dir):
    ds = make_dataset(EMPLOYEES, "corrupt")
    path = data_dir / "decisions" / f"{ds.id}.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    copy = fresh_copy(ds)
    assert copy.decisions == [] and views.build_view(copy).rows == 30
    assert not path.exists() and list(path.parent.glob(f"{ds.id}.json.unreadable-*"))
