"""Numbers from the bundled demo files that the product promises (one Olympics load for all checks)."""

from __future__ import annotations

import json

import pytest

from app import issues, loader, service, views

OLYMPICS = loader.DATASET_DIR / "olympics_athletes"


@pytest.fixture(scope="module")
def olympics():
    path = OLYMPICS / "athlete_events.csv"
    if not path.exists():
        pytest.skip("Olympics demo file not present")
    return loader.load_csv(path.read_bytes(), path.name, dataset_id="test-olympics")


def test_noc_regions_loads_230_rows():
    path = OLYMPICS / "noc_regions.csv"
    ds = loader.load_csv(path.read_bytes(), path.name, dataset_id="test-noc")
    assert ds.rows == 230


def test_olympics_duplicates_and_double_counting(olympics):
    found = {i.id: i for i in issues.detected(olympics)}
    assert found["duplicate_rows:all"].affected_rows == 1385

    gold = json.dumps([{"column": "Medal", "op": "=", "value": "Gold"}])
    rows = service.group_json(olympics, "decisions", "NOC", None, "count", False, gold)
    assert rows["groups"][0] == {"key": "USA", "value": 2638, "rows": 2638}

    unit = next(o["op"] for o in found["double_counting:event-games-noc-medal"].options if o["op"])
    service.add_decision(olympics, unit, "double_counting:event-games-noc-medal", None)
    medals = service.group_json(olympics, "decisions", "NOC", None, "count", True, gold)
    assert medals["groups"][0] == {"key": "USA", "value": 1131, "rows": 2638}
    assert medals["count_unit"] == "medals"
    assert views.build_view(olympics).rows == 271116
