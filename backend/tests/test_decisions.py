"""Re-answering a question replaces its decision; toggling/deleting in any order stays safe."""

from __future__ import annotations

import pytest
from conftest import EMPLOYEES

from app import issues, service, views

EMAIL = "fake_unique_id:email"
FLAG = {"op": "flag_duplicates", "key": ["Email"], "label": "Shared Email"}


@pytest.fixture
def ds(make_dataset):
    return make_dataset(EMPLOYEES, "emp")


def everything_loads(ds):
    service.profile_json(ds, "decisions")
    service.profile_json(ds, "original")
    service.rows_json(ds, "decisions", 0, 10, None, "asc", None, None, None)
    return {i["id"]: i for i in issues.all_json(ds)}


def test_blind_test_repro_flag_off_then_keep(ds):
    first = service.add_decision(ds, FLAG, EMAIL, "No")
    assert everything_loads(ds)[EMAIL]["status"] == "flagged"
    service.set_enabled(ds, first, False)
    assert everything_loads(ds)[EMAIL]["status"] == "open"
    keep = service.add_decision(ds, None, EMAIL, "Yes")
    assert [d.id for d in ds.decisions] == [keep.id]          # replaced, not added
    assert everything_loads(ds)[EMAIL]["status"] == "kept"
    again = service.add_decision(ds, FLAG, EMAIL, "No")
    assert [d.id for d in ds.decisions] == [again.id]
    service.remove_decision(ds, again)
    assert everything_loads(ds)[EMAIL]["status"] == "open"


def test_replace_keeps_position_in_chain(ds):
    a = service.add_decision(ds, {"op": "mark_missing", "column": "Name", "values": ["Name1"]}, None, None)
    service.add_decision(ds, FLAG, EMAIL, None)
    b = service.add_decision(ds, {"op": "mark_missing", "column": "Name", "values": ["Name2"]}, None, None)
    new = service.add_decision(ds, None, EMAIL, None)
    assert [d.id for d in ds.decisions] == [a.id, new.id, b.id]


def test_dependent_decision_breaks_instead_of_breaking_dataset(ds):
    split = service.add_decision(ds, {"op": "split_column", "column": "Dept_Region", "sep": "-",
                                      "into": ["Dept", "Region"]}, None, None)
    merge = service.add_decision(ds, {"op": "merge_values", "column": "Dept", "from": ["Ops"], "to": "Operations"},
                                 None, None)
    service.set_enabled(ds, split, False)
    everything_loads(ds)
    assert merge.broken and not merge.enabled and "Dept" in merge.error
    service.set_enabled(ds, split, True)
    service.set_enabled(ds, merge, True)
    assert not merge.broken and "Dept" in views.build_view(ds).columns


def test_options_only_use_current_columns(ds):
    service.add_decision(ds, {"op": "split_column", "column": "Dept_Region", "sep": "-", "into": ["Dept", "Region"]},
                         None, None)
    columns = views.build_view(ds).columns
    for issue in issues.all_json(ds):
        for opt in issue["options"]:
            if opt["op"] and "column" in opt["op"]:
                assert opt["op"]["column"] in columns


def test_one_not_sure_option_per_question(ds):
    for issue in issues.all_json(ds):
        skips = [o for o in issue["options"] if o.get("skip")]
        assert len(skips) == (1 if issue["kind"] == "question" and issue["question"] else 0)


def test_negative_phone_offers_a_visible_fix(ds):
    issue = next(i for i in issues.all_json(ds) if i["id"] == "impossible_values:phone-negative")
    for opt in issue["options"]:
        if opt["op"]:
            assert views.preview(ds, opt["op"])["affected_rows"] > 0


def test_rows_are_typed(ds):
    service.add_decision(ds, {"op": "change_type", "column": "Amount", "to": "decimal"}, None, None)
    out = service.rows_json(ds, "decisions", 0, 2, None, "asc", None, None, None)
    row = dict(zip(out["columns"], out["rows"][0]))
    assert row["Amount"] == 1000 and row["Score"] == 0 and row["Phone"] == -5551234000
    assert out["row_numbers"] == [1, 2] and out["total_unfiltered"] == 30


def test_reset(ds):
    service.add_decision(ds, FLAG, EMAIL, None)
    service.reset(ds)
    assert ds.decisions == [] and views.build_view(ds).table == ds.table
