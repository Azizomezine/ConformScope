"""Room labels read off a plan by Muse Spark."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass

import jsonschema

from conformscope.plan import Plan

MODEL = "muse-spark-1.3"

ROOM_TYPES = ["living", "bedroom", "kitchen", "bathroom", "wc",
              "corridor", "entrance", "storage", "other"]
ROOM_TYPE = {"type": "string", "enum": ROOM_TYPES}

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
                    "room_type": ROOM_TYPE,
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


def _load(text: str, schema: dict, what: str):
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Muse Spark reply is not JSON: {text[:80]!r}") from error
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as error:
        raise ValueError(f"Muse Spark reply does not match the {what} schema: {error.message}") from error
    return data


def to_pixels(norm: int, size: int) -> int:
    return min(max(round(norm * size / 1000), 0), size - 1)


def parse_rooms(text: str, width: int, height: int) -> RoomReading:
    """Turn Muse Spark's JSON reply into labels placed in plan pixels."""
    data = _load(text, ROOMS_SCHEMA, "rooms")
    rooms = [
        RoomLabel(r["name"], r["room_type"], to_pixels(r["x"], width), to_pixels(r["y"], height), r["area_m2"])
        for r in data["rooms"]
    ]
    return RoomReading(scale=data.get("scale"), rooms=rooms)


def _ask(client, image_url: str, prompt: str, name: str, schema: dict) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]}],
        response_format={"type": "json_schema", "json_schema": {"name": name, "schema": schema}},
    )
    return response.choices[0].message.content


def read_rooms(client, plan: Plan) -> tuple[str, RoomReading]:
    """Ask Muse Spark for the room labels; return its raw reply and the parsed reading."""
    text = _ask(client, plan.data_url(), PROMPT, "Rooms", ROOMS_SCHEMA)
    return text, parse_rooms(text, plan.width, plan.height)


TYPES_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["rooms"],
    "properties": {
        "rooms": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["number", "room_type"],
                "properties": {
                    "number": {"type": "integer", "description": "The number drawn in the room"},
                    "room_type": ROOM_TYPE,
                },
            },
        },
    },
}

TYPES_PROMPT = (
    "This is an architectural floor plan of a home. Some rooms are outlined in colour with a "
    "large red number in them. For each numbered room, say what kind of room it is, judging "
    "from the fixtures drawn in it (toilet, bath, shower, sink, hob) and from where it sits in "
    "the home. Only answer for the numbers you can see."
)


def parse_types(text: str) -> dict[int, str]:
    data = _load(text, TYPES_SCHEMA, "room types")
    return {r["number"]: r["room_type"] for r in data["rooms"]}


def type_rooms(client, png: bytes) -> tuple[str, dict[int, str]]:
    """Ask Muse Spark to type the numbered rooms drawn on `png`, in one call."""
    url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    text = _ask(client, url, TYPES_PROMPT, "RoomTypes", TYPES_SCHEMA)
    return text, parse_types(text)


_POINT = {"type": "integer", "description": "0-1000 grid over the image"}

DIMENSION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["dimension"],
    "properties": {
        "dimension": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "required": ["value_m", "x1", "y1", "x2", "y2"],
            "properties": {
                "value_m": {"type": "number", "description": "The written length, in metres"},
                "x1": _POINT, "y1": _POINT, "x2": _POINT, "y2": _POINT,
            },
        },
    },
}

DIMENSION_PROMPT = (
    "This is an architectural floor plan. Find the longest dimension line with a length "
    "written on it (for example 3.40 or 340). Give that length in metres and the two ends of "
    "the line it measures, as points on a 0-1000 grid over the image (x to the right, y down). "
    "If no length is written on the plan, answer null."
)


@dataclass(frozen=True)
class Dimension:
    value_m: float
    x1: int
    y1: int
    x2: int
    y2: int


def parse_dimension(text: str, width: int, height: int) -> Dimension | None:
    d = _load(text, DIMENSION_SCHEMA, "dimension")["dimension"]
    if d is None:
        return None
    return Dimension(d["value_m"], to_pixels(d["x1"], width), to_pixels(d["y1"], height),
                     to_pixels(d["x2"], width), to_pixels(d["y2"], height))


def read_dimension(client, plan: Plan) -> tuple[str, Dimension | None]:
    """Ask Muse Spark for one written dimension and its two ends, to scale a picture."""
    text = _ask(client, plan.data_url(), DIMENSION_PROMPT, "Dimension", DIMENSION_SCHEMA)
    return text, parse_dimension(text, plan.width, plan.height)
