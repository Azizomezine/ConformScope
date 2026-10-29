import json

import numpy as np
import pytest

from conformscope.fixtures import assign_rooms, split_fixtures
from conformscope.labels import parse_rooms
from conformscope.plan import load_plan
from conformscope.rooms import measure_rooms
from test_labels import RECORDED
from test_rooms import SAMPLE, _fake_client


def _box(shape, x0, y0, x1, y1):
    mask = np.zeros(shape, bool)
    mask[y0:y1, x0:x1] = True
    return mask


SHAPE = (200, 300)


def test_each_detector_becomes_one_fixture_per_symbol():
    placards = _box(SHAPE, 10, 10, 40, 80) | _box(SHAPE, 200, 10, 260, 40)
    cells = _box(SHAPE, 100, 100, 130, 130)
    toilets = _box(SHAPE, 150, 150, 170, 180)

    fixtures = split_fixtures(placards, cells, toilets)

    assert sorted(f.kind for f in fixtures) == ["appliance", "placard", "placard", "toilet"]
    toilet = next(f for f in fixtures if f.kind == "toilet")
    assert toilet.origin == (150, 150) and toilet.crop.shape == (30, 20)


def test_a_toilet_the_cell_finder_also_took_is_only_a_toilet():
    toilets = _box(SHAPE, 150, 150, 170, 180)
    cells = _box(SHAPE, 148, 148, 172, 182)  # the same symbol, a little wider

    fixtures = split_fixtures(np.zeros(SHAPE, bool), cells, toilets)

    assert [f.kind for f in fixtures] == ["toilet"]


def test_a_speck_left_over_is_not_a_fixture():
    cells = _box(SHAPE, 100, 100, 102, 102)

    assert split_fixtures(np.zeros(SHAPE, bool), cells, np.zeros(SHAPE, bool)) == []


def test_an_appliance_in_a_bathroom_or_wc_is_a_washbasin():
    kitchen = _box(SHAPE, 0, 0, 150, 200)
    bathroom = _box(SHAPE, 150, 0, 300, 200)
    fixtures = split_fixtures(np.zeros(SHAPE, bool),
                              _box(SHAPE, 20, 20, 50, 50) | _box(SHAPE, 200, 20, 230, 50),
                              np.zeros(SHAPE, bool))

    assign_rooms(fixtures, [kitchen, bathroom], ["kitchen", "bathroom"])

    by_room = {f.room: f.kind for f in fixtures}
    assert by_room == {0: "appliance", 1: "washbasin"}


def test_a_placard_in_a_bathroom_stays_a_placard_and_one_outside_every_room_has_none():
    bathroom = _box(SHAPE, 150, 0, 300, 200)
    fixtures = split_fixtures(_box(SHAPE, 200, 20, 260, 50) | _box(SHAPE, 10, 10, 40, 40),
                              np.zeros(SHAPE, bool), np.zeros(SHAPE, bool))

    assign_rooms(fixtures, [bathroom], ["bathroom"])

    assert sorted((f.kind, f.room) for f in fixtures if f.room is not None) == [("placard", 0)]
    assert any(f.room is None for f in fixtures)


def test_a_fixture_belongs_to_the_room_holding_most_of_it():
    left = _box(SHAPE, 0, 0, 105, 200)
    right = _box(SHAPE, 105, 0, 300, 200)
    fixtures = split_fixtures(_box(SHAPE, 100, 50, 140, 80), np.zeros(SHAPE, bool),
                              np.zeros(SHAPE, bool))

    assign_rooms(fixtures, [left, right], ["bedroom", "bedroom"])

    assert fixtures[0].room == 1


@pytest.mark.skipif(not SAMPLE.exists(), reason="private sample plan not present")
def test_sample_plan_fixtures_are_found_and_placed_in_their_rooms():
    plan = load_plan(SAMPLE)
    reading = parse_rooms(RECORDED, plan.width, plan.height)
    client, _ = _fake_client(json.dumps({"rooms": []}))

    result = measure_rooms(client, SAMPLE, plan, reading)

    kinds = [f.kind for f in result.fixtures]
    assert kinds.count("placard") == 13
    assert kinds.count("toilet") == 7
    assert kinds.count("appliance") + kinds.count("washbasin") >= 10
    for fixture in result.fixtures:
        assert len(fixture.polygon_px) >= 3 and len(fixture.polygon_m) >= 3
        if fixture.room is not None:
            assert result.fixtures.index(fixture) in result.rooms[fixture.room].fixtures
    for fixture in result.fixtures:
        if fixture.kind == "washbasin":
            assert result.rooms[fixture.room].room_type in ("wc", "bathroom")
