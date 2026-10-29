"""Room labels read off a plan by Muse Spark."""

from __future__ import annotations

import json
from dataclasses import dataclass

import jsonschema

from conformscope.plan import Plan

MODEL = "muse-spark-1.3"

ROOMS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["scale", "rooms"],
    "properties": {
        "scale": {"type": ["string", "null"], "description": "Scale written on the plan, e.g. 1:50"},
        "rooms": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "area_m2", "room_type", "x", "y"],
                "properties": {
                    "name": {"type": "string", "description": "Label text without the area"},
                    "area_m2": {"type": ["number", "null"], "description": "Area written on the plan"},
                    "room_type": {
                        "type": "string",
                        "enum": ["living", "bedroom", "kitchen", "bathroom", "wc",
                                 "corridor", "entrance", "storage", "other"],
                    },
                    "x": {"type": "integer", "description": "Label centre, 0-1000 grid"},
                    "y": {"type": "integer", "description": "Label centre, 0-1000 grid"},
                },
            },
        },
    },
}

PROMPT = (
    "This is an architectural floor plan of a home. List every room that has a written "
    "label. For each, give the label text, the area written next to it (m², as a number, or "
    "null), the room type, and the centre of the label as a "
    "point on a 0-1000 grid over the image (x to the right, y down). Also give the drawing "
    "scale if one is written on the plan."
)


@dataclass(frozen=True)
class RoomLabel:
    name: str
    room_type: str
    x: int
    y: int
    area_m2: float | None = None


@dataclass(frozen=True)
class RoomReading:
    scale: str | None
    rooms: list[RoomLabel]


def parse_rooms(text: str, width: int, height: int) -> RoomReading:
    """Turn Muse Spark's JSON reply into labels placed in plan pixels."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Muse Spark reply is not JSON: {text[:80]!r}") from error
    try:
        jsonschema.validate(data, ROOMS_SCHEMA)
    except jsonschema.ValidationError as error:
        raise ValueError(f"Muse Spark reply does not match the rooms schema: {error.message}") from error

    def to_pixels(norm: int, size: int) -> int:
        return min(max(round(norm * size / 1000), 0), size - 1)

    rooms = [
        RoomLabel(r["name"], r["room_type"], to_pixels(r["x"], width), to_pixels(r["y"], height), r["area_m2"])
        for r in data["rooms"]
    ]
    return RoomReading(scale=data.get("scale"), rooms=rooms)


def read_rooms(client, plan: Plan) -> tuple[str, RoomReading]:
    """Ask Muse Spark for the room labels; return its raw reply and the parsed reading."""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": plan.data_url()}},
        ]}],
        response_format={"type": "json_schema",
                         "json_schema": {"name": "Rooms", "schema": ROOMS_SCHEMA}},
    )
    text = response.choices[0].message.content
    return text, parse_rooms(text, plan.width, plan.height)
