"""Walk the plan: which rooms a wheelchair reaches, and where it stops (CONTEXT.md, #14).

The rooms are the nodes and the doors (#13) the edges. The wheelchair crosses only a door
wide enough; a narrow one is a **stop** it does not pass, and the rooms behind it are
unreachable, blocked by it. A room where the turning circle fails is reached all the same
-- a wheelchair can roll into a room it cannot turn in -- and is a stop it rolls through.

It starts outside, through the entrance door, the way a visitor arrives; with no entrance
door, in a hall. The auditor may start it from any room.

The route is one continuous line for the icon to follow: depth first, room centre to
doorway to the next room's centre, backing out the way it came. Straight lines: it may cut
the corner of an L-shaped room.

Pure, on the rooms and doors as the API returns them, so a stored sheet can be walked
again from any room without measuring it again.
"""

from __future__ import annotations

from collections import deque

FALLBACK_START = ("entrance", "corridor", "living")


def _centre(room: dict) -> tuple[float, float]:
    if room.get("circle_px"):
        x, y = room["circle_px"]
        return float(x), float(y)
    xs, ys = zip(*room["polygon_px"])
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _middle(door: dict) -> tuple[float, float]:
    (ax, ay), (bx, by) = door["doorway_px"]
    return (ax + bx) / 2, (ay + by) / 2


def _passes(door: dict) -> bool:
    a, b = door["rooms"]
    return door.get("ok") is True and a is not None and b is not None and a != b


def _between_rooms(door: dict) -> bool:
    a, b = door["rooms"]
    return a is not None and b is not None and a != b


def _narrow_reason(door: dict) -> str:
    return f"{door['width_m']:.2f} m door, needs {door['required_m']:.2f} m"


def _fallback(rooms: list[dict]) -> int:
    for room_type in FALLBACK_START:
        found = next((i for i, room in enumerate(rooms) if room.get("room_type") == room_type), None)
        if found is not None:
            return found
    return 0


def walk(rooms: list[dict], doors: list[dict], start: int | None = None) -> dict:
    """The walk from `start` (a room index), or from the entrance by default."""
    if not rooms:
        return {"start": None, "reached": [], "unreachable": [], "stops": [], "route": [],
                "verdict": "No rooms to walk through"}

    route: list[dict] = []
    stops: list[dict] = []
    reached: list[int] = []
    blocked: dict[int, int] = {}  # a narrow door met -> the room on its far side

    def step(point, event, room=None, door=None):
        route.append({"point_px": [round(point[0], 1), round(point[1], 1)], "room": room,
                      "door": door, "event": event})

    def stop_at_door(i: int, far: int | None):
        if all(s.get("door") != i for s in stops):
            stops.append({"kind": "door", "door": i, "room": None, "reason": _narrow_reason(doors[i])})
        if far is not None:
            blocked.setdefault(i, far)

    def explore(room: int):
        reached.append(room)
        here = _centre(rooms[room])
        step(here, "enter", room)
        if rooms[room].get("conforme") is False:
            step(here, "cannot_turn", room)
            stops.append({"kind": "turn", "door": None, "room": room,
                          "reason": "Can't turn around here: no Ø1.50 m circle fits"})
        for i, door in enumerate(doors):
            if room not in door["rooms"] or not _between_rooms(door):
                continue
            a, b = door["rooms"]
            far = b if a == room else a
            if far in reached:
                continue
            if door.get("ok") is False:
                step(_middle(door), "blocked_door", door=i)
                stop_at_door(i, far)
                step(here, "back", room)
            elif _passes(door):
                step(_middle(door), "through", door=i)
                explore(far)
                step(_middle(door), "through", door=i)
                step(here, "back", room)

    entrances = [i for i, door in enumerate(doors)
                 if (door["rooms"][0] is None) != (door["rooms"][1] is None)]
    if start is not None:
        begin = {"room": start, "door": None}
        step(_centre(rooms[start]), "start", start)
        explore(start)
    elif entrances:
        begin = {"room": None, "door": entrances[0]}
        for i in entrances:
            inside = next(r for r in doors[i]["rooms"] if r is not None)
            if inside in reached:
                continue
            step(_middle(doors[i]), "start", door=i)
            if doors[i].get("ok") is True:
                explore(inside)
            elif doors[i].get("ok") is False:
                step(_middle(doors[i]), "blocked_door", door=i)
                stop_at_door(i, inside)
    else:
        first = _fallback(rooms)
        begin = {"room": first, "door": None}
        step(_centre(rooms[first]), "start", first)
        explore(first)

    unreachable = _unreachable(rooms, doors, reached, blocked)
    return {"start": begin, "reached": sorted(reached), "unreachable": unreachable,
            "stops": stops, "route": route,
            "verdict": f"The wheelchair reaches {len(reached)} of {len(rooms)} rooms"}


def _unreachable(rooms, doors, reached, blocked) -> list[dict]:
    """Every room not reached, with the narrow door that keeps it out: the first one met
    on the walk whose far side leads to it through any door at all. None when no door
    leads there."""
    by: dict[int, int] = {}
    for door_i, far in blocked.items():
        queue = deque([far])
        while queue:
            room = queue.popleft()
            if room in reached or room in by:
                continue
            by[room] = door_i
            for door in doors:
                if room in door["rooms"] and _between_rooms(door):
                    a, b = door["rooms"]
                    queue.append(b if a == room else a)
    return [{"room": i, "blocked_by": by.get(i)} for i in range(len(rooms)) if i not in reached]
