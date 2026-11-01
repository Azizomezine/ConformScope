import math

from conformscope.walk import walk


def _room(name, x, conforme=True, room_type="bedroom"):
    return {"name": name, "room_type": room_type, "conforme": conforme,
            "circle_px": (x, 100.0), "polygon_px": [(x - 40, 60), (x + 40, 60), (x + 40, 140), (x - 40, 140)]}


def _door(a, b, x, ok=True, width=0.80):
    return {"rooms": [a, b], "ok": ok, "width_m": width, "required_m": 0.80 if None not in (a, b) else 0.90,
            "role": "interior" if None not in (a, b) else "entrance",
            "doorway_px": [(x, 80.0), (x, 120.0)]}


# hall (0) — living (1) — bedroom (2), and the hall's entrance from the landing on its left.
ROOMS = [_room("Hall", 100, room_type="entrance"), _room("Living", 200, room_type="living"), _room("Bedroom", 300)]
ENTRANCE = _door(None, 0, 50, ok=True, width=0.90)


def test_the_walk_reaches_every_room_through_wide_doors():
    result = walk(ROOMS, [ENTRANCE, _door(0, 1, 150), _door(1, 2, 250)])

    assert result["reached"] == [0, 1, 2]
    assert result["unreachable"] == [] and result["stops"] == []
    assert result["verdict"] == "The wheelchair reaches 3 of 3 rooms"


def test_a_narrow_door_hides_the_rooms_behind_it_and_names_itself():
    doors = [ENTRANCE, _door(0, 1, 150), _door(1, 2, 250, ok=False, width=0.70)]

    result = walk(ROOMS, doors)

    assert result["reached"] == [0, 1]
    assert result["unreachable"] == [{"room": 2, "blocked_by": 2}]
    (stop,) = result["stops"]
    assert stop["kind"] == "door" and stop["door"] == 2
    assert "0.70 m" in stop["reason"] and "0.80 m" in stop["reason"]


def test_a_room_where_the_circle_fails_is_reached_and_is_a_stop():
    rooms = [ROOMS[0], _room("Living", 200, conforme=False, room_type="living"), ROOMS[2]]

    result = walk(rooms, [ENTRANCE, _door(0, 1, 150), _door(1, 2, 250)])

    assert result["reached"] == [0, 1, 2]  # it rolls on through
    assert [(s["kind"], s["room"]) for s in result["stops"]] == [("turn", 1)]
    assert any(step["event"] == "cannot_turn" and step["room"] == 1 for step in result["route"])


def test_a_narrow_entrance_stops_the_walk_at_once():
    entrance = _door(None, 0, 50, ok=False, width=0.80)

    result = walk(ROOMS, [entrance, _door(0, 1, 150), _door(1, 2, 250)])

    assert result["reached"] == []
    assert [s["kind"] for s in result["stops"]] == ["door"]
    assert all(u["blocked_by"] == 0 for u in result["unreachable"])
    assert result["verdict"] == "The wheelchair reaches 0 of 3 rooms"


def test_with_no_entrance_the_walk_starts_in_the_hall():
    rooms = [_room("Bedroom", 100), _room("Hall", 200, room_type="entrance"), _room("Living", 300, room_type="living")]

    result = walk(rooms, [_door(0, 1, 150), _door(1, 2, 250)])

    assert result["start"] == {"room": 1, "door": None}
    assert result["route"][0]["room"] == 1 and result["reached"] == [0, 1, 2]


def test_the_walk_can_start_from_any_room():
    result = walk(ROOMS, [ENTRANCE, _door(0, 1, 150), _door(1, 2, 250, ok=False, width=0.70)], start=2)

    assert result["start"] == {"room": 2, "door": None}
    assert result["reached"] == [2]
    assert result["unreachable"] == [{"room": 0, "blocked_by": 2}, {"room": 1, "blocked_by": 2}]


def test_the_route_is_continuous_and_backs_out_the_way_it_came():
    # Living has two dead ends: the walk must come back through Living between them.
    rooms = ROOMS + [_room("Bathroom", 200, room_type="bathroom")]
    doors = [ENTRANCE, _door(0, 1, 150), _door(1, 2, 250), _door(1, 3, 200)]
    doors[3]["doorway_px"] = [(180.0, 140.0), (220.0, 140.0)]

    route = walk(rooms, doors)["route"]

    assert route[0]["event"] == "start"
    rooms_in_order = [step["room"] for step in route if step["event"] in ("enter", "back")]
    assert rooms_in_order[:4] == [0, 1, 2, 1]  # into the bedroom, then back to the living room
    assert 3 in rooms_in_order
    for before, after in zip(route, route[1:]):
        # Each step goes to a door or a room next to the last one: no jump across the plan.
        assert math.dist(before["point_px"], after["point_px"]) <= 120


def test_a_door_not_checked_or_with_one_room_on_both_sides_is_not_crossed():
    doors = [ENTRANCE, _door(0, 1, 150, ok=None), _door(0, 0, 120)]

    result = walk(ROOMS, doors)

    assert result["reached"] == [0]
    assert {u["room"] for u in result["unreachable"]} == {1, 2}
    assert all(u["blocked_by"] is None for u in result["unreachable"])


def test_a_plan_with_no_rooms_has_an_empty_walk():
    result = walk([], [])

    assert result["route"] == [] and result["reached"] == []
    assert result["verdict"] == "No rooms to walk through"
