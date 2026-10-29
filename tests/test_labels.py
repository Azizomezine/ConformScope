import json
from types import SimpleNamespace

import pytest

from conformscope.labels import RoomLabel, parse_rooms, read_rooms
from conformscope.plan import Plan


def _reply(payload):
    return json.dumps(payload)


def test_normalised_points_become_plan_pixels():
    text = _reply({"scale": "1:50", "rooms": [
        {"name": "Chambre 1", "room_type": "bedroom", "x": 500, "y": 250},
    ]})

    reading = parse_rooms(text, width=2000, height=1000)

    assert reading.scale == "1:50"
    assert reading.rooms == [RoomLabel("Chambre 1", "bedroom", 1000, 250)]


def test_points_off_the_plan_are_clamped_inside_it():
    text = _reply({"scale": None, "rooms": [
        {"name": "SdB", "room_type": "bathroom", "x": 1000, "y": -20},
    ]})

    (room,) = parse_rooms(text, width=400, height=300).rooms

    assert (room.x, room.y) == (399, 0)


def test_a_reply_that_breaks_the_schema_is_a_clear_error():
    with pytest.raises(ValueError, match="rooms"):
        parse_rooms(_reply({"scale": None}), width=10, height=10)


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
