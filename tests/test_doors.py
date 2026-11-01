import numpy as np
import pytest

from conformscope.doors import Arc, door_body, doors_ok, find_doors, judge, remove_doors, snap

PX_PER_M = 50  # 0.80 m is 40 px


def _rooms(shape, *boxes):
    """A room index: -1 everywhere, then each box its own room."""
    index = np.full(shape, -1, np.int32)
    for i, (x0, y0, x1, y1) in enumerate(boxes):
        index[y0:y1, x0:x1] = i
    return index


def _box(shape, x0, y0, x1, y1):
    mask = np.zeros(shape, bool)
    mask[y0:y1, x0:x1] = True
    return mask


# Two rooms side by side, split by a wall at x 100-104 with a doorway at y 60-100.
SHAPE = (200, 220)
TWO_ROOMS = ((10, 10, 100, 190), (104, 10, 210, 190))


def _wall_with_gap():
    return _box(SHAPE, 100, 10, 104, 60) | _box(SHAPE, 100, 100, 104, 190)


def _door_into_right_room(radius=40):
    # Hinged at the bottom jamb, closed along the wall line, swinging open into the right room.
    return Arc(hinge=(102, 100), ends=((102, 100 - radius), (102 + radius, 100)))


@pytest.mark.parametrize("measured, width", [(0.81, 0.80), (0.88, 0.90), (0.76, 0.76), (0.93, 0.90),
                                             (1.36, 1.36)])
def test_a_measured_leaf_snaps_to_a_catalogue_size_within_3_cm(measured, width):
    assert snap(measured) == width


def test_a_door_joins_the_two_rooms_either_side_of_its_doorway():
    index = _rooms(SHAPE, *TWO_ROOMS)

    (door,) = find_doors([_door_into_right_room()], index, _wall_with_gap(), np.zeros(SHAPE, bool), PX_PER_M)

    assert sorted(door.rooms) == [0, 1]
    (ax, ay), (bx, by) = door.doorway
    assert ax == bx == 102  # along the wall line, not the open leaf
    assert door.measured_m == pytest.approx(0.80, abs=0.01)


def test_a_leaf_opening_against_a_wall_is_still_not_the_doorway():
    # The leaf opens flat against a wall in the right room, so a wall runs past its tip too.
    index = _rooms(SHAPE, *TWO_ROOMS)
    walls = _wall_with_gap() | _box(SHAPE, 145, 95, 150, 105)

    (door,) = find_doors([_door_into_right_room()], index, walls, np.zeros(SHAPE, bool), PX_PER_M)

    assert sorted(door.rooms) == [0, 1]


def test_an_interior_door_needs_80_cm():
    index = _rooms(SHAPE, *TWO_ROOMS)

    narrow = find_doors([_door_into_right_room(35)], index, _wall_with_gap(), np.zeros(SHAPE, bool), PX_PER_M)[0]
    wide = find_doors([_door_into_right_room(41)], index, _wall_with_gap(), np.zeros(SHAPE, bool), PX_PER_M)[0]

    assert (narrow.role, narrow.required_m, narrow.ok) == ("interior", 0.80, False)
    assert (wide.width_m, wide.ok) == (0.80, True)
    assert "0.70 m" in narrow.verdict and "needs 0.80 m" in narrow.verdict


def test_a_door_out_of_every_room_is_the_entrance_and_needs_90_cm():
    index = _rooms(SHAPE, TWO_ROOMS[1])  # the left side is a landing: no room

    (door,) = find_doors([_door_into_right_room(42)], index, _wall_with_gap(), np.zeros(SHAPE, bool), PX_PER_M)

    assert (door.role, door.required_m, door.ok) == ("entrance", 0.90, False)
    assert "outside every room" in door.verdict


def test_a_door_with_no_room_on_either_side_is_not_checked():
    index = _rooms(SHAPE)

    (door,) = find_doors([_door_into_right_room()], index, _wall_with_gap(), np.zeros(SHAPE, bool), PX_PER_M)

    assert (door.role, door.ok) == ("communs", None)
    assert doors_ok([door]) is None


def test_two_arcs_meeting_in_one_doorway_are_one_double_door():
    index = _rooms(SHAPE, *TWO_ROOMS)
    wall = _box(SHAPE, 100, 10, 104, 40) | _box(SHAPE, 100, 120, 104, 190)
    top = Arc(hinge=(102, 40), ends=((102, 80), (142, 40)))       # leaves meet at y 80
    bottom = Arc(hinge=(102, 120), ends=((102, 85), (137, 120)))  # this leaf is 0.70 m

    (door,) = find_doors([top, bottom], index, wall, np.zeros(SHAPE, bool), PX_PER_M)

    assert len(door.arcs) == 2
    assert door.width_m == 0.80  # the wider leaf
    assert sorted(door.rooms) == [0, 1]


def test_an_arc_swinging_onto_a_placard_is_not_a_door():
    index = _rooms(SHAPE, TWO_ROOMS[1])
    placard = _box(SHAPE, 60, 55, 100, 105)  # the placard stands where the left room was

    assert find_doors([_door_into_right_room()], index, _wall_with_gap(), placard, PX_PER_M) == []


def test_a_click_inside_the_swing_removes_the_door():
    index = _rooms(SHAPE, *TWO_ROOMS)
    doors = find_doors([_door_into_right_room()], index, _wall_with_gap(), np.zeros(SHAPE, bool), PX_PER_M)

    assert remove_doors(doors, [(115, 85)]) == []          # inside the quarter circle
    assert remove_doors(doors, [(90, 85), (180, 180)]) == doors  # beside it, and far off


def test_the_home_passes_when_every_judged_door_does():
    index = _rooms(SHAPE, *TWO_ROOMS)
    good = find_doors([_door_into_right_room(41)], index, _wall_with_gap(), np.zeros(SHAPE, bool), PX_PER_M)
    bad = find_doors([_door_into_right_room(35)], index, _wall_with_gap(), np.zeros(SHAPE, bool), PX_PER_M)

    assert doors_ok(good) is True
    assert doors_ok(good + bad) is False
    assert doors_ok([]) is None


def test_a_door_becomes_a_line_on_the_plan():
    index = _rooms(SHAPE, *TWO_ROOMS)
    (door,) = find_doors([_door_into_right_room()], index, _wall_with_gap(), np.zeros(SHAPE, bool), PX_PER_M)

    body = door_body(door, to_plan=2.0)

    assert {"rooms", "role", "width_m", "measured_m", "required_m", "ok", "verdict", "doorway_px"} <= body.keys()
    assert sorted(body["doorway_px"]) == [(204.0, 120.0), (204.0, 200.0)]


def test_judging_names_the_role_it_assumed():
    assert judge((0, 1), 0.81)[0:3] == ("interior", 0.80, 0.80)
    assert judge((None, 1), 0.91)[0:3] == ("entrance", 0.90, 0.90)


# --- on plans --------------------------------------------------------------------------

def _sample():
    import json
    from conformscope.labels import parse_rooms
    from conformscope.plan import load_plan
    from test_labels import RECORDED
    from test_rooms import SAMPLE, _fake_client

    plan = load_plan(SAMPLE)
    reading = parse_rooms(RECORDED, plan.width, plan.height)
    client, _ = _fake_client(json.dumps({"rooms": []}))
    return client, plan, reading


from test_rooms import SAMPLE  # noqa: E402


@pytest.mark.skipif(not SAMPLE.exists(), reason="private sample plan not present")
def test_sample_plan_doors_are_judged_and_join_rooms():
    from conformscope.rooms import measure_rooms

    client, plan, reading = _sample()
    result = measure_rooms(client, SAMPLE, plan, reading)

    assert len(result.doors) >= 15
    interior = [d for d in result.doors if d["role"] == "interior"]
    assert len(interior) >= 8
    assert all(d["width_m"] in (0.80, 0.90) and d["ok"] for d in interior)
    assert result.doors_ok in (True, False)
    for i, door in enumerate(result.doors):
        for room in door["rooms"]:
            if room is not None:
                assert i in result.rooms[room].doors


@pytest.mark.skipif(not SAMPLE.exists(), reason="private sample plan not present")
def test_sample_plan_a_removed_door_is_gone_until_the_corrections_are_cleared():
    import pymupdf
    from conformscope.rooms import measure_rooms

    client, plan, reading = _sample()
    before = measure_rooms(client, SAMPLE, plan, reading)
    door = next(d for d in before.doors if d["role"] == "interior")
    # The correction is anchored in PDF points; the swing's middle is in plan pixels.
    with pymupdf.open(SAMPLE) as doc:
        pt_per_px = doc[0].rect.width / plan.width
    swing = door["swing_px"]
    point = [swing[0] * pt_per_px, swing[1] * pt_per_px]

    after = measure_rooms(client, SAMPLE, plan, reading, corrections=[{"kind": "remove_door", "point": point}])

    assert len(after.doors) == len(before.doors) - 1


def test_a_picture_plan_has_no_doors_and_says_so():
    from test_fixtures import TOILET_BOX, _picture, _picture_client
    from conformscope.rooms import picture_rooms

    plan, reading = _picture()
    client, _ = _picture_client([TOILET_BOX], sam_error=RuntimeError("down"))

    result = picture_rooms(client, plan, reading)

    assert result.doors == [] and result.doors_ok is None
    assert any("Doors are read from vector PDFs only" in w for w in result.warnings)
