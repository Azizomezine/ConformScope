"""Doors: each one's width judged, and the two rooms it joins (CONTEXT.md, issue #13).

A door is known by its drawn swing arc, on a vector plan only. The arc's radius is the
leaf, which architects draw at the door's nominal width (0.80, 0.90 m), so that is what is
judged, snapped to the catalogue size it is drawn at. The passage utile is never drawn, so
it is never judged.

Of an arc's two radii, the **doorway** is the one that closes on the far jamb: the wall goes
on just past its tip. The other is the leaf standing open, its tip in free floor. Two arcs
whose closed tips meet are one double door, hinge to hinge.

Which width a door needs is read from its two sides: two rooms make an interior door
(0.80 m), a room and no room the entrance (0.90 m), and no room at all a door of the communs,
shown but not checked.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from conformscope.extract import _arc_hinge

CATALOGUE_M = (0.60, 0.70, 0.80, 0.90, 1.00)
SNAP_M = 0.03          # a leaf this close to a catalogue size is that size
DOUBLE_M = 0.15        # two closed tips this close meet in one doorway
JAMB_M = (0.05, 0.15)  # how far past a tip the wall is looked for
SIDE_M = (0.15, 0.30, 0.45)  # how far either side of the doorway its rooms are looked for
REQUIRED_M = {"interior": 0.80, "entrance": 0.90}

Point = tuple[float, float]


@dataclass(frozen=True)
class Arc:
    """A door's swing on the grid: its hinge and the tips of its two radii."""
    hinge: Point
    ends: tuple[Point, Point]

    @property
    def radius_px(self) -> float:
        return max(math.dist(self.hinge, end) for end in self.ends)


@dataclass(eq=False)
class Door:
    arcs: list[Arc]
    doorway: tuple[Point, Point]
    rooms: tuple[int | None, int | None]
    measured_m: float
    width_m: float
    role: str                 # "interior" | "entrance" | "communs"
    required_m: float | None
    ok: bool | None           # None: not checked
    verdict: str
    warnings: list[str] = field(default_factory=list)


def snap(measured_m: float) -> float:
    nearest = min(CATALOGUE_M, key=lambda size: abs(size - measured_m))
    return nearest if abs(nearest - measured_m) <= SNAP_M + 1e-9 else round(measured_m, 2)


def judge(rooms: tuple[int | None, int | None], measured_m: float):
    """(role, required width, judged width, ok, verdict) for a door with these sides."""
    width = snap(measured_m)
    shown = f"{width:.2f} m" + (f" (measured {measured_m:.2f} m)" if abs(width - measured_m) >= 0.005 else "")
    sides = [room for room in rooms if room is not None]
    if not sides:
        return "communs", None, width, None, f"Not in any measured room: not checked · {shown}"
    role = "interior" if len(sides) == 2 else "entrance"
    required = REQUIRED_M[role]
    ok = width >= required - 1e-9
    label = ("Interior door" if role == "interior"
             else "Entrance door (one side is outside every room)")
    return role, required, width, ok, f"{label} · {shown} · needs {required:.2f} m"


def _inside(shape, x: float, y: float) -> bool:
    return 0 <= int(round(y)) < shape[0] and 0 <= int(round(x)) < shape[1]


def _closes_on_a_jamb(hinge: Point, tip: Point, walls: np.ndarray, px_per_m: float) -> bool:
    """Whether the wall goes on just past this tip, in the radius's direction."""
    length = math.dist(hinge, tip)
    if length == 0:
        return False
    dx, dy = (tip[0] - hinge[0]) / length, (tip[1] - hinge[1]) / length
    for distance in np.linspace(JAMB_M[0], JAMB_M[1], 5) * px_per_m:
        x, y = tip[0] + dx * distance, tip[1] + dy * distance
        if _inside(walls.shape, x, y) and walls[int(round(y)), int(round(x))]:
            return True
    return False


def _sides(a: Point, b: Point, rooms: np.ndarray, walls: np.ndarray, placards: np.ndarray,
           px_per_m: float) -> tuple[list[int | None], bool]:
    """The room on either side of the doorway a-b (None for no room), and whether a
    placard stands on a side."""
    length = math.dist(a, b) or 1.0
    nx, ny = -(b[1] - a[1]) / length, (b[0] - a[0]) / length
    found: list[int | None] = []
    placard = False
    for sign in (1, -1):
        votes: Counter = Counter()
        for t in (0.25, 0.5, 0.75):
            px, py = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
            for distance in SIDE_M:
                x, y = px + sign * nx * distance * px_per_m, py + sign * ny * distance * px_per_m
                if not _inside(rooms.shape, x, y):
                    continue
                iy, ix = int(round(y)), int(round(x))
                if placards[iy, ix]:
                    placard = True
                if walls[iy, ix]:
                    continue
                votes[int(rooms[iy, ix])] += 1
        in_room = {room: n for room, n in votes.items() if room >= 0}
        found.append(max(in_room, key=in_room.get) if in_room else None)
    return found, placard


def _doubles(arcs: list[Arc], px_per_m: float) -> list[tuple[Arc, ...]]:
    """Arcs grouped into doors: two whose tips meet are one double door."""
    used: set[int] = set()
    groups: list[tuple[Arc, ...]] = []
    for i, first in enumerate(arcs):
        if i in used:
            continue
        partner = next((j for j in range(i + 1, len(arcs)) if j not in used and any(
            math.dist(p, q) <= DOUBLE_M * px_per_m for p in first.ends for q in arcs[j].ends)), None)
        used.add(i)
        if partner is None:
            groups.append((first,))
        else:
            used.add(partner)
            groups.append((first, arcs[partner]))
    return groups


def find_doors(arcs: list[Arc], rooms: np.ndarray, walls: np.ndarray, placards: np.ndarray,
               px_per_m: float) -> list[Door]:
    """Every door the arcs draw. `rooms` holds each pixel's room index, -1 for none."""
    doors = []
    for group in _doubles(arcs, px_per_m):
        if len(group) == 2:
            doorway = (group[0].hinge, group[1].hinge)
        else:
            (arc,) = group
            # The doorway parts two different places; the open leaf stands in one room. A
            # leaf opening flat against a wall has a wall past its tip too, so the jamb only
            # breaks a tie.
            doorway = max(((arc.hinge, tip) for tip in arc.ends), key=lambda seg: (
                len(set(_sides(*seg, rooms, walls, placards, px_per_m)[0])),
                _closes_on_a_jamb(*seg, walls, px_per_m)))
        sides, placard = _sides(*doorway, rooms, walls, placards, px_per_m)
        if placard:
            continue  # the placard's own door
        measured = max(arc.radius_px for arc in group) / px_per_m
        role, required, width, ok, verdict = judge((sides[0], sides[1]), measured)
        doors.append(Door(list(group), doorway, (sides[0], sides[1]), round(measured, 2), width,
                          role, required, ok, verdict))
    return doors


def _in_swing(arc: Arc, point: Point) -> bool:
    """Whether a point lies in the quarter circle the leaf sweeps."""
    vx, vy = point[0] - arc.hinge[0], point[1] - arc.hinge[1]
    if math.hypot(vx, vy) > arc.radius_px:
        return False
    (ax, ay), (bx, by) = [(end[0] - arc.hinge[0], end[1] - arc.hinge[1]) for end in arc.ends]
    span = abs(math.atan2(ax * by - ay * bx, ax * bx + ay * by))
    to_a = abs(math.atan2(ax * vy - ay * vx, ax * vx + ay * vy))
    to_b = abs(math.atan2(bx * vy - by * vx, bx * vx + by * vy))
    return abs(to_a + to_b - span) < 1e-6


def remove_doors(doors: list[Door], points: list[Point]) -> list[Door]:
    """The doors no point lands in: an auditor's removals, as grid pixels."""
    return [door for door in doors
            if not any(_in_swing(arc, point) for arc in door.arcs for point in points)]


def doors_ok(doors: list[Door]) -> bool | None:
    """Whether every judged door is wide enough; None when no door is judged."""
    judged = [door.ok for door in doors if door.ok is not None]
    return all(judged) if judged else None


def swing_middle(arc: Arc) -> Point:
    """A point halfway into the quarter circle: where a click removes the door."""
    units = [((x - arc.hinge[0]) / max(math.dist(arc.hinge, (x, y)), 1e-6),
              (y - arc.hinge[1]) / max(math.dist(arc.hinge, (x, y)), 1e-6)) for x, y in arc.ends]
    dx, dy = units[0][0] + units[1][0], units[0][1] + units[1][1]
    norm = math.hypot(dx, dy) or 1.0
    reach = 0.5 * arc.radius_px
    return arc.hinge[0] + dx / norm * reach, arc.hinge[1] + dy / norm * reach


def door_arcs(paths, dpi: int) -> list[Arc]:
    """The detected swing paths as arcs on the grid they were rasterised on."""
    scale = dpi / 72.0
    arcs = []
    for path in paths:
        curves = [item for item in path["items"] if item[0] == "c"]
        if not curves:
            continue
        start, end = curves[0][1], curves[-1][4]
        hx, hy = _arc_hinge(start, end, curves)
        arcs.append(Arc((hx * scale, hy * scale),
                        ((start.x * scale, start.y * scale), (end.x * scale, end.y * scale))))
    return arcs


def door_body(door: Door, to_plan: float) -> dict:
    """A door as the API returns it: its doorway, and a point in its swing, on the plan image."""
    def plan(point: Point) -> tuple[float, float]:
        return round(point[0] * to_plan, 1), round(point[1] * to_plan, 1)

    return {"rooms": list(door.rooms), "role": door.role, "width_m": door.width_m,
            "measured_m": door.measured_m, "required_m": door.required_m, "ok": door.ok,
            "verdict": door.verdict, "doorway_px": [plan(p) for p in door.doorway],
            "swing_px": plan(swing_middle(door.arcs[0]))}
