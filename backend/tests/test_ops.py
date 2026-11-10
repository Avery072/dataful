"""Each op in the fixed vocabulary compiles to SQL over the previous view and does what it says."""

from __future__ import annotations

import pytest
from conftest import view_rows

from app import ops, service, views

CSV = """id,name,city,amount,joined,ts,qty,a,b
1,Ann,NYC,"$1,200",4/2/2021,964982703,53.0,X,1
2,Bob,nyc,N/A,2021-05-01,964982704,2.0,Y,2
3,Ann,NYC,"$1,200",4/2/2021,964982703,53.0,X,1
4,Cy,,300,12/31/2020,964982705,7.0,Z,3
"""


@pytest.fixture
def ds(make_dataset):
    return make_dataset(CSV, "ops")


def apply(ds, op):
    service.add_decision(ds, op, None, None)
    return view_rows(ds)


def column(ds, op, name):
    cols, rows = apply(ds, op)
    return [r[cols.index(name)] for r in rows]


def test_mark_missing(ds):
    assert column(ds, {"op": "mark_missing", "column": "amount", "values": ["N/A"]}, "amount")[1] is None


def test_fill_blank(ds):
    assert column(ds, {"op": "fill_blank", "column": "city", "value": "Unknown"}, "city")[3] == "Unknown"


def test_change_type_decimal_integer_date(ds):
    assert column(ds, {"op": "change_type", "column": "amount", "to": "decimal"}, "amount") == ["1200", None, "1200", "300"]
    assert column(ds, {"op": "change_type", "column": "qty", "to": "integer"}, "qty")[0] == "53"
    assert column(ds, {"op": "change_type", "column": "joined", "to": "date"}, "joined")[:2] == ["2021-04-02", "2021-05-01"]
    assert column(ds, {"op": "change_type", "column": "ts", "to": "date"}, "ts")[0] == "2000-07-30"


def test_split_and_combine(ds):
    cols, rows = apply(ds, {"op": "combine_columns", "columns": ["a", "b"], "sep": "-", "into": "ab"})
    assert "ab" in cols and "a" not in cols and rows[0][cols.index("ab")] == "X-1"
    cols, rows = apply(ds, {"op": "split_column", "column": "ab", "sep": "-", "into": ["left", "right"]})
    assert (rows[0][cols.index("left")], rows[0][cols.index("right")]) == ("X", "1")


def test_merge_values_and_keep_separate(ds):
    assert column(ds, {"op": "merge_values", "column": "city", "from": ["nyc"], "to": "NYC"}, "city")[1] == "NYC"
    cols, rows = apply(ds, {"op": "keep_separate", "column": "name", "values": ["Ann", "Bob"]})
    assert len(rows) == 4


def test_count_unit(ds):
    apply(ds, {"op": "set_count_unit", "columns": ["name"], "label": "people"})
    view = views.build_view(ds)
    assert view.count_unit == {"columns": ["name"], "label": "people"}
    result = views.group(view, "city", "count", None, True, "TRUE")
    assert {g["key"]: g["value"] for g in result["groups"]} == {"NYC": 1, "nyc": 1}
    assert result["excluded"]["no_key"] == 1


def test_row_ops(ds):
    _, rows = apply(ds, {"op": "drop_rows", "where": [{"column": "city", "op": "is_missing"}]})
    assert len(rows) == 3
    cols, rows = apply(ds, {"op": "flag_rows", "where": [{"column": "name", "op": "=", "value": "Bob"}], "label": "B"})
    assert [r[cols.index(ops.FLAG_COLUMN)] for r in rows] == [None, "B", None]
    _, rows = apply(ds, {"op": "remove_duplicates", "columns": ["name", "city", "amount"]})
    assert len(rows) == 2


def test_merge_records_and_flag_duplicates(ds):
    cols, rows = apply(ds, {"op": "flag_duplicates", "key": ["name"], "label": "Same name"})
    assert [r[cols.index(ops.FLAG_COLUMN)] for r in rows] == ["Same name", None, "Same name", None]
    _, rows = apply(ds, {"op": "merge_records", "key": ["name"], "keep": "first"})
    assert len(rows) == 3


def test_invalid_op_is_rejected_and_nothing_changes(ds):
    with pytest.raises(ops.OpError):
        service.add_decision(ds, {"op": "mark_missing", "column": "nope", "values": ["x"]}, None, None)
    with pytest.raises(ops.OpError):
        service.add_decision(ds, {"op": "explode"}, None, None)
    assert ds.decisions == []


def test_filter_can_compare_two_columns(make_dataset):
    ds = make_dataset("id,Signup,LastBuy\n1,2021-05-01,2021-04-01\n2,2021-01-01,2021-02-01\n3,,2021-02-01\n", "cmp")
    op = {"op": "flag_rows", "where": [{"column": "Signup", "op": ">", "other_column": "LastBuy"}], "label": "bought before signup"}
    assert "Signup is above LastBuy" in ops.plain(ops.validate(op, ["id", "Signup", "LastBuy"]))
    cols, rows = apply(ds, op)
    assert [r[cols.index("Flag")] for r in rows] == ["bought before signup", None, None]
