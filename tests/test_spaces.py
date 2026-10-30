import json

import numpy as np
import pytest

from conformscope.fixtures import FixtureMask
from conformscope.labels import parse_rooms
from conformscope.plan import load_plan
from conformscope.rooms import measure_rooms
from conformscope.spaces import (
    accessible_wc,
    check_spaces,
    find_space,
    front_touch,
    wcs_without_toilet,
)
from test_labels import RECORDED
from test_rooms import SAMPLE, _fake_client

PX_PER_M = 50  # 0.80 m is 40 px, 1.30 m is 65 px


def _box(shape, x0, y0, x1, y1):
    mask = np.zeros(shape, bool)
    mask[y0:y1, x0:x1] = True
    return mask


def _fixture(kind, shape, x0, y0, x1, y1, room=0):
    return FixtureMask(kind, (x0, y0), np.ones((y1 - y0, x1 - x0), bool), room)


def test_a_toilet_with_room_beside_it_has_a_transfer_space():
    shape = (120, 160)
    room = _box(shape, 10, 10, 150, 110)            # 2.80 x 2.00 m
    toilet = _fixture("toilet", shape, 10, 50, 38, 70)  # against the left wall

    (space,) = check_spaces([toilet], [room], np.zeros(shape, bool), PX_PER_M)

    assert space.kind == "transfer" and space.fits
    x, y, w, h = space.rect
    assert sorted((w, h)) == [40, 65]
    assert not (room[y:y + h, x:x + w] == 0).any()


def test_a_toilet_boxed_in_by_walls_has_no_transfer_space_but_a_best_attempt():
    shape = (80, 80)
    room = _box(shape, 10, 10, 60, 70)              # 1.00 x 1.20 m
    toilet = _fixture("toilet", shape, 10, 10, 30, 38)

    (space,) = check_spaces([toilet], [room], np.zeros(shape, bool), PX_PER_M)

    assert not space.fits
    assert space.rect is not None


def test_another_fixture_inside_the_rectangle_fails_it():
    shape = (120, 160)
    room = _box(shape, 10, 10, 80, 110)             # 1.40 x 2.00 m
    toilet = _fixture("toilet", shape, 10, 50, 38, 70)
    basin = _fixture("washbasin", shape, 38, 10, 80, 110)  # fills the rest of the floor

    spaces = check_spaces([toilet, basin], [room], np.zeros(shape, bool), PX_PER_M)

    assert not spaces[0].fits


def test_walls_block_the_space_and_a_door_swing_is_never_given_as_a_blocker():
    # check_spaces only takes walls: a door swing over the space cannot fail it.
    shape = (120, 160)
    room = _box(shape, 10, 10, 150, 110)
    toilet = _fixture("toilet", shape, 10, 50, 38, 70)
    walls = _box(shape, 38, 10, 40, 110) | _box(shape, 10, 70, 150, 72) | _box(shape, 10, 48, 150, 50)

    (space,) = check_spaces([toilet], [room], walls, PX_PER_M)

    assert not space.fits


def test_the_washbasin_space_is_in_front_of_it_and_marked_to_confirm():
    shape = (120, 160)
    room = _box(shape, 10, 10, 150, 110)
    basin = _fixture("washbasin", shape, 60, 10, 90, 35)  # against the top wall

    (space,) = check_spaces([basin], [room], np.zeros(shape, bool), PX_PER_M)

    assert space.kind == "washbasin" and space.fits and space.to_confirm
    x, y, w, h = space.rect
    assert y >= 35  # below the basin, not beside it against the wall
    assert x < 90 and x + w > 60


def test_the_front_of_a_fixture_is_its_side_facing_the_most_floor():
    free = _box((100, 100), 0, 30, 100, 100)  # the wall is above the fixture
    fixture = FixtureMask("washbasin", (40, 30), np.ones((20, 30), bool))

    touch = front_touch(fixture, free, depth_px=3)

    ys, xs = np.nonzero(touch)
    assert ys.min() >= 50 and xs.min() >= 40 and xs.max() < 70


def test_placards_and_appliances_get_no_space():
    shape = (120, 160)
    room = _box(shape, 10, 10, 150, 110)
    fixtures = [_fixture("placard", shape, 10, 10, 50, 40), _fixture("appliance", shape, 100, 10, 130, 40)]

    assert check_spaces(fixtures, [room], np.zeros(shape, bool), PX_PER_M) == [None, None]


def test_find_space_with_nothing_to_touch_is_none():
    free = np.ones((100, 100), bool)

    assert find_space(free, np.zeros_like(free), 40, 65) is None


def test_one_passing_toilet_makes_the_home_have_an_accessible_wc():
    shape = (120, 160)
    room = _box(shape, 10, 10, 150, 110)
    good = _fixture("toilet", shape, 10, 50, 38, 70)
    spaces = check_spaces([good], [room], np.zeros(shape, bool), PX_PER_M)
    bad = check_spaces([_fixture("toilet", shape, 10, 10, 30, 38)],
                       [_box(shape, 10, 10, 60, 70)], np.zeros(shape, bool), PX_PER_M)

    assert accessible_wc(spaces + bad) is True
    assert accessible_wc(bad) is False
    assert accessible_wc([None]) is None


def test_a_wc_with_no_toilet_found_is_named():
    toilet = FixtureMask("toilet", (0, 0), np.ones((2, 2), bool), room=1)

    assert wcs_without_toilet(["wc", "wc", "bathroom", "bedroom"], [toilet]) == [0]


@pytest.mark.parametrize("fits, kind, text", [
    (True, "transfer", "Transfer space found"),
    (False, "transfer", "No 0.80 × 1.30 m transfer space beside this toilet"),
    (True, "washbasin", "Washbasin space found (rule to confirm)"),
    (False, "washbasin", "No 0.80 × 1.30 m space in front of this washbasin (rule to confirm)"),
])
def test_the_verdict_says_found_never_compliant(fits, kind, text):
    from conformscope.spaces import SpaceFit

    assert SpaceFit(kind, fits, (0, 0, 1, 1)).verdict == text


def test_a_space_becomes_a_polygon_on_the_plan_and_in_metres():
    from conformscope.spaces import SpaceFit, space_body

    body = space_body(SpaceFit("transfer", True, (100, 50, 40, 65)), px_per_m=50, to_plan=2.0)

    assert body["kind"] == "transfer" and body["fits"] and not body["to_confirm"]
    assert body["verdict"] == "Transfer space found"
    assert body["polygon_px"] == [(200.0, 100.0), (280.0, 100.0), (280.0, 230.0), (200.0, 230.0)]
    assert body["polygon_m"] == [(2.0, 1.0), (2.8, 1.0), (2.8, 2.3), (2.0, 2.3)]


@pytest.mark.skipif(not SAMPLE.exists(), reason="private sample plan not present")
def test_sample_plan_toilets_and_washbasins_carry_their_spaces():
    plan = load_plan(SAMPLE)
    reading = parse_rooms(RECORDED, plan.width, plan.height)
    client, _ = _fake_client(json.dumps({"rooms": []}))

    result = measure_rooms(client, SAMPLE, plan, reading)

    for fixture in result.fixtures:
        if fixture.kind == "toilet":
            assert fixture.space["kind"] == "transfer"
        elif fixture.kind == "washbasin":
            assert fixture.space["kind"] == "washbasin" and fixture.space["to_confirm"]
        else:
            assert fixture.space is None
    assert result.accessible_wc in (True, False)
