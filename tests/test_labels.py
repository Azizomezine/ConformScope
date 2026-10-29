import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from conformscope.labels import RoomLabel, parse_rooms, read_rooms
from conformscope.plan import Plan

# Muse Spark's reply on Plan_Logement_Niveau_02 (live spike, 2026-10-29), with the area
# split out of the name by hand to match the current schema.
RECORDED = (Path(__file__).parent / "fixtures" / "muse_rooms_reply.json").read_text(encoding="utf-8")


def _reply(payload):
    return json.dumps(payload)


def _room(**overrides):
    return {"name": "Chambre 1", "area_m2": 12.5, "room_type": "bedroom", "x": 500, "y": 250} | overrides


def test_recorded_reply_parses_into_eight_bedrooms():
    reading = parse_rooms(RECORDED, width=1754, height=1240)

    assert reading.scale == "1:100"
    assert len(reading.rooms) == 8
    assert {room.room_type for room in reading.rooms} == {"bedroom"}
    assert reading.rooms[0] == RoomLabel("Bedroom", "bedroom", 203, 213, 15.31)


def test_normalised_points_become_plan_pixels():
    reading = parse_rooms(_reply({"scale": "1:50", "rooms": [_room()]}), width=2000, height=1000)

    assert reading.rooms == [RoomLabel("Chambre 1", "bedroom", 1000, 250, 12.5)]


def test_area_may_be_missing_from_the_plan():
    (room,) = parse_rooms(_reply({"scale": None, "rooms": [_room(area_m2=None)]}), 10, 10).rooms

    assert room.area_m2 is None


def test_points_off_the_plan_are_clamped_inside_it():
    text = _reply({"scale": None, "rooms": [_room(x=1000, y=-20)]})

    (room,) = parse_rooms(text, width=400, height=300).rooms

    assert (room.x, room.y) == (399, 0)


def test_a_reply_without_rooms_is_a_clear_error():
    with pytest.raises(ValueError, match="rooms"):
        parse_rooms(_reply({"scale": None}), width=10, height=10)


def test_an_unknown_room_type_is_a_clear_error():
    with pytest.raises(ValueError, match="garage"):
        parse_rooms(_reply({"scale": None, "rooms": [_room(room_type="garage")]}), 10, 10)


def test_a_room_with_a_text_coordinate_is_a_clear_error():
    with pytest.raises(ValueError, match="schema"):
        parse_rooms(_reply({"scale": None, "rooms": [_room(x="left")]}), 10, 10)


def test_a_reply_that_is_not_json_is_a_clear_error():
    with pytest.raises(ValueError, match="JSON"):
        parse_rooms("Sure! Here are the rooms:", width=10, height=10)


def test_read_rooms_sends_the_plan_with_a_json_schema():
    sent = {}

    def create(**kwargs):
        sent.update(kwargs)
        message = SimpleNamespace(content=_reply({"scale": None, "rooms": []}))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    plan = Plan(png=b"\x89PNG", width=10, height=10)

    read_rooms(client, plan)

    assert sent["model"] == "muse-spark-1.3"
    assert sent["response_format"]["type"] == "json_schema"
    image = sent["messages"][0]["content"][1]
    assert image["image_url"]["url"].startswith("data:image/png;base64,")
