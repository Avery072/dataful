"""Spelling variants of one column are ONE issue with one recode mapping to clean targets."""

from __future__ import annotations

from conftest import view_rows

from app import issues, ops, service

GENDERS = ["F"] * 30 + ["f "] * 31 + ["female"] * 29 + ["FEMALE"] * 28 + ["M"] * 30 + ["m "] * 30 + ["male"] * 28 + ["MALE"] * 29
CSV = "id,Gender,City\n" + "\n".join(f"{i},{g},{'Pune' if i % 2 else 'pune'}" for i, g in enumerate(GENDERS))


def _category_issues(ds):
    return {i.columns[0]: i for i in issues.detected(ds) if i.family == "inconsistent_categories"}


def test_recode_values_rewrites_many_spellings_at_once(make_dataset):
    ds = make_dataset(CSV, "recode")
    service.add_decision(ds, {"op": "recode_values", "column": "Gender",
                              "mapping": {"f ": "F", "female": "F", "FEMALE": "F"}}, None, None)
    cols, rows = view_rows(ds)
    assert {r[cols.index("Gender")] for r in rows} == {"F", "M", "m ", "male", "MALE"}


def test_recode_values_validation():
    try:
        ops.validate({"op": "recode_values", "column": "Gender", "mapping": {"a": "a"}}, ["Gender"])
    except ops.OpError:
        pass
    else:
        raise AssertionError("a mapping that changes nothing should be rejected")


def test_one_issue_per_column_with_clean_targets(make_dataset):
    ds = make_dataset(CSV, "gender")
    found = _category_issues(ds)
    gender = found["Gender"]
    assert gender.kind == "question" and "2 values in 8 ways" in gender.title
    full = gender.options[0]["op"]["mapping"]
    assert set(full.values()) <= {"female", "FEMALE", "male", "MALE"}          # never 'f ' or 'F'
    assert len({v.lower() for v in full.values()}) == 2
    assert all(t == t.strip() for t in full.values())
    labels = [o["label"] for o in gender.options]
    assert "Only fix capitals and spaces" in labels
    assert found["City"].kind == "fix" and found["City"].confidence == "certain"


def test_partial_fix_leaves_the_abbreviation_question_open(make_dataset):
    ds = make_dataset(CSV, "partial")
    gender = _category_issues(ds)["Gender"]
    tidy = next(o for o in gender.options if o["label"] == "Only fix capitals and spaces")
    service.add_decision(ds, tidy["op"], gender.id, None)
    after = _category_issues(ds)["Gender"]
    assert after.id != gender.id and issues.status(ds, after)[0] == "open"
    service.add_decision(ds, after.options[0]["op"], after.id, None)
    cols, rows = view_rows(ds)
    assert len({r[cols.index("Gender")] for r in rows}) == 2
