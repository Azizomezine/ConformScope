"""Human corrections to the rooms a plan was cut into (issue #6, backend).

A correction is anchored in PDF points, never in a room index or number:
those reshuffle on every re-cut (see ``geometry.Room.anchor_pt``), while a
point inside a room is a property of the physical space.  Two kinds exist:

* ``Merge`` -- a nook the walls alone cut off (or a room cut in two) belongs
  to another room.  It stores a PDF-point point inside the region to merge
  and a PDF-point point inside the room that should claim it, so both ends
  can be found again after re-cutting.
* ``DrawnWall`` -- a wall the plan is missing, drawn by hand between two
  PDF-point endpoints.  On replay the segment is rasterised into the
  barrier mask a little longer than drawn (``DRAWN_WALL_OVERSHOOT_M``
  beyond each end), so a click just short of the far wall still closes
  the gap and ``geometry.segment_seeded`` / ``segment_rooms`` split the
  room on the next cut.

Corrections are a JSON-serialisable list, stored alongside a plan (for
example as ``corrections.json`` under ``.data/plans/<id>/``, next to
``reading.json``; ``api.py`` can persist them later with
``corrections_to_json`` / ``corrections_from_json`` or the ``*_data``
pair -- this module does not touch ``api.py``).  Every room a correction
touches carries provenance the way ``MeasuredRoom.type_source`` records
where its type came from: functions here that rebuild a ``MeasuredRoom``
set ``outline_source`` to ``"merged"`` or ``"wall"`` (``"auto"`` when no
correction touched it).

Everything is pure and mask-based: no input mask is mutated, and replaying
the same stored corrections always produces the same masks and fields.
Coordinates: correction points are PDF points (top-left origin, y down,
as in the rest of the pipeline).  Masks live on the raster grid the walls
are drawn on (``rooms.DPI``), so a PDF point lands on grid pixel
``point * pt_to_px`` with ``pt_to_px = DPI / 72`` by default; synthetic
callers may pass ``pt_to_px=1.0`` to work in grid pixels directly.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

import cv2
import numpy as np

from conformscope.rooms import DPI, MeasuredRoom, _circle, _crop, outline

# How far past each drawn end a drawn wall reaches, in metres of building.
DRAWN_WALL_OVERSHOOT_M = 0.15

# Grid pixels per PDF point on the grid the walls are rasterised on.
PT_TO_PX = DPI / 72

OUTLINE_SOURCES = ("auto", "merged", "wall")

Point = tuple[float, float]


@dataclass
class CorrectedRoom(MeasuredRoom):
    """A ``MeasuredRoom`` rebuilt by a correction, with outline provenance.

    ``rooms.MeasuredRoom`` has no ``outline_source`` field and this issue
    may not edit ``rooms.py``, so rebuilt rooms are this subclass: the
    extra field is a real dataclass field (``dataclasses.asdict`` keeps
    it, as ``api.py`` serialises rooms that way), defaulting to ``"auto"``.
    """

    outline_source: str = "auto"


def _point(value) -> Point:
    x, y = value
    return (float(x), float(y))


def _point_list(point: Point) -> list[float]:
    return [float(point[0]), float(point[1])]


# --- corrections ----------------------------------------------------------------------


@dataclass(frozen=True)
class Merge:
    """Merge the region around ``point`` into the room around ``target_point``.

    Both points are PDF points: ``point`` inside the region to merge (the
    nook), ``target_point`` inside the room that should claim it.
    """

    point: Point
    target_point: Point
    kind: ClassVar[str] = "merge"

    def __post_init__(self) -> None:
        object.__setattr__(self, "point", _point(self.point))
        object.__setattr__(self, "target_point", _point(self.target_point))

    @property
    def claimed_point(self) -> Point:
        """Alias for ``point``: the point inside the region being claimed."""
        return self.point

    @property
    def source_point(self) -> Point:
        return self.point

    def to_dict(self) -> dict:
        return {"kind": "merge", "point": _point_list(self.point),
                "target_point": _point_list(self.target_point)}

    @classmethod
    def from_dict(cls, data: dict) -> "Merge":
        return cls(point=data["point"], target_point=data["target_point"])


@dataclass(frozen=True)
class DrawnWall:
    """A missing wall drawn between two PDF-point endpoints."""

    start: Point
    end: Point
    kind: ClassVar[str] = "wall"

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", _point(self.start))
        object.__setattr__(self, "end", _point(self.end))

    @property
    def endpoints(self) -> tuple[Point, Point]:
        return (self.start, self.end)

    @property
    def a(self) -> Point:
        return self.start

    @property
    def b(self) -> Point:
        return self.end

    def to_dict(self) -> dict:
        return {"kind": "wall", "start": _point_list(self.start),
                "end": _point_list(self.end)}

    @classmethod
    def from_dict(cls, data: dict) -> "DrawnWall":
        if "start" in data or "end" in data:
            return cls(start=data["start"], end=data["end"])
        start, end = data["endpoints"]
        return cls(start=start, end=end)


# Aliases matching the issue's vocabulary.
MergeCorrection = Merge
DrawnWallCorrection = DrawnWall
Wall = DrawnWall

Correction = Merge | DrawnWall


def correction_to_dict(correction: Correction) -> dict:
    """One correction as a JSON-serialisable dict (points as ``[x, y]``)."""
    if isinstance(correction, (Merge, DrawnWall)):
        return correction.to_dict()
    raise TypeError(f"Not a correction: {correction!r}")


def correction_from_dict(data: dict) -> Correction:
    """One correction back from :func:`correction_to_dict`'s dict."""
    kind = str(data.get("kind", "")).lower()
    if kind == "merge":
        return Merge.from_dict(data)
    if kind in ("wall", "drawn_wall", "drawn-wall", "drawnwall"):
        return DrawnWall.from_dict(data)
    raise ValueError(f"Unknown correction kind: {data.get('kind')!r}")


def corrections_to_data(corrections) -> list[dict]:
    """The stored form of a plan's corrections: a list of plain dicts."""
    return [correction_to_dict(c) for c in corrections]


def corrections_from_data(data) -> list[Correction]:
    """Corrections back from :func:`corrections_to_data`'s list."""
    return [correction_from_dict(d) for d in data]


def corrections_to_json(corrections) -> str:
    """The stored corrections as JSON text, for ``corrections.json``."""
    return json.dumps(corrections_to_data(corrections), ensure_ascii=False)


def corrections_from_json(text) -> list[Correction]:
    """Corrections back from JSON text (or an already-parsed list)."""
    data = json.loads(text) if isinstance(text, (str, bytes)) else text
    return corrections_from_data(data)


def corrections_path(plan_dir: str | Path) -> Path:
    """Where a plan's corrections live alongside its ``reading.json``."""
    return Path(plan_dir) / "corrections.json"


def dump_corrections(plan_dir: str | Path, corrections) -> Path:
    """Write a plan's corrections next to its reading; returns the path."""
    path = corrections_path(plan_dir)
    path.write_text(corrections_to_json(corrections), encoding="utf-8")
    return path


def load_corrections(plan_dir: str | Path) -> list[Correction]:
    """A plan's stored corrections, or ``[]`` when none were stored."""
    path = corrections_path(plan_dir)
    if not path.exists():
        return []
    return corrections_from_json(path.read_text(encoding="utf-8"))


# --- points on masks ------------------------------------------------------------------


def pdf_to_px(point, pt_to_px: float = PT_TO_PX) -> tuple[int, int]:
    """A PDF-point point as a grid pixel ``(x, y)``."""
    return (int(round(float(point[0]) * pt_to_px)),
            int(round(float(point[1]) * pt_to_px)))


def point_in_mask(mask: np.ndarray, point, pt_to_px: float = PT_TO_PX) -> bool:
    """Whether the PDF-point ``point`` lands inside ``mask``."""
    x, y = pdf_to_px(point, pt_to_px)
    return 0 <= y < mask.shape[0] and 0 <= x < mask.shape[1] and bool(mask[y, x])


def find_mask_index(masks, point, pt_to_px: float = PT_TO_PX) -> int | None:
    """Index of the first mask holding the PDF-point ``point``, or None."""
    for i, mask in enumerate(masks):
        if point_in_mask(mask, point, pt_to_px):
            return i
    return None


# Backwards-friendly alias.
find_room_index = find_mask_index


# --- merging --------------------------------------------------------------------------


@dataclass(eq=False)
class MergeResult:
    """A merged room's mask and everything recomputed from it."""

    mask: np.ndarray
    area_m2: float
    polygon_px: list
    polygon_m: list
    circle_m: float                 # diameter, as ``MeasuredRoom.circle_m``
    circle_px: tuple | None
    outline_source: str = "merged"
    target_index: int | None = None
    merged_index: int | None = None

    @property
    def source_index(self) -> int | None:
        return self.merged_index


@dataclass(eq=False)
class DrawnWallResult:
    """Kept for symmetry: the wall mask after a drawn wall enters it."""

    mask: np.ndarray
    outline_source: str = "wall"


def _measure(mask: np.ndarray, px_per_m: float, to_plan: float,
             blocked: np.ndarray | None = None):
    """(polygon_px, polygon_m, area_m2, circle_m, circle_px) for a mask."""
    origin, crop = _crop(mask)
    polygon_px, polygon_m, area_m2 = outline(crop, origin, px_per_m, to_plan)
    free = crop
    if blocked is not None:
        h, w = crop.shape
        free = crop & ~blocked[origin[1]:origin[1] + h, origin[0]:origin[0] + w]
    circle_m, (cx, cy) = _circle(free, origin, px_per_m)
    return polygon_px, polygon_m, area_m2, circle_m, (cx * to_plan, cy * to_plan)


def merge_masks(target_mask: np.ndarray, region_mask: np.ndarray,
                px_per_m: float, to_plan: float = 1.0,
                blocked: np.ndarray | None = None) -> MergeResult:
    """Union of two masks, with area, outline and largest circle recomputed."""
    if target_mask.shape != region_mask.shape:
        raise ValueError(f"Mask shapes differ: {target_mask.shape} vs {region_mask.shape}")
    mask = np.asarray(target_mask, bool) | np.asarray(region_mask, bool)
    if not mask.any():
        raise ValueError("Cannot merge empty masks")
    polygon_px, polygon_m, area_m2, circle_m, circle_px = _measure(
        mask, px_per_m, to_plan, blocked)
    return MergeResult(mask=mask, area_m2=area_m2, polygon_px=polygon_px,
                       polygon_m=polygon_m, circle_m=circle_m,
                       circle_px=circle_px, outline_source="merged")


def apply_merge(masks, correction, px_per_m: float, pt_to_px: float = PT_TO_PX,
                to_plan: float = 1.0,
                blocked: np.ndarray | None = None) -> MergeResult:
    """Merge the region a ``Merge`` points at into the room it targets.

    ``masks`` is the sequence of room masks (bool arrays, one shape).  The
    region mask is the one holding ``correction.point`` and the target the
    one holding ``correction.target_point`` -- both PDF points, so the
    merge survives a re-cut that renumbers the rooms.  Returns the union
    mask with its area, outline and largest circle recomputed via
    ``rooms.outline`` / ``rooms._circle``; the inputs are not mutated.
    """
    if isinstance(correction, dict):
        correction = correction_from_dict(correction)
    if not isinstance(correction, Merge):
        raise TypeError(f"apply_merge needs a Merge, got {correction!r}")
    masks = list(masks)
    target_index = find_mask_index(masks, correction.target_point, pt_to_px)
    if target_index is None:
        raise ValueError(f"No room mask holds the merge target {correction.target_point}")
    merged_index = find_mask_index(masks, correction.point, pt_to_px)
    if merged_index is None:
        raise ValueError(f"No room mask holds the region to merge {correction.point}")
    result = merge_masks(masks[target_index], masks[merged_index],
                         px_per_m, to_plan, blocked)
    result.target_index = target_index
    result.merged_index = merged_index
    return result


# --- drawn walls ----------------------------------------------------------------------


def extended_endpoints_px(correction, px_per_m: float,
                          pt_to_px: float = PT_TO_PX,
                          overshoot_m: float = DRAWN_WALL_OVERSHOOT_M):
    """A drawn wall's endpoints in grid pixels, overshot at both ends.

    Each end is pushed ``overshoot_m`` metres (``overshoot_m * px_per_m``
    grid pixels) past the drawn point, along the segment's direction.
    Returns ``((x1, y1), (x2, y2))`` as float grid pixels.
    """
    if isinstance(correction, dict):
        correction = correction_from_dict(correction)
    if isinstance(correction, (tuple, list)):
        correction = DrawnWall(start=correction[0], end=correction[1])
    start = (float(correction.start[0]) * pt_to_px, float(correction.start[1]) * pt_to_px)
    end = (float(correction.end[0]) * pt_to_px, float(correction.end[1]) * pt_to_px)
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length == 0:
        raise ValueError("A drawn wall needs two distinct endpoints")
    if px_per_m <= 0:
        raise ValueError(f"px_per_m must be positive, got {px_per_m}")
    ux, uy = dx / length, dy / length
    over = float(overshoot_m) * float(px_per_m)
    return ((start[0] - ux * over, start[1] - uy * over),
            (end[0] + ux * over, end[1] + uy * over))


def drawn_wall_mask(shape, correction, px_per_m: float,
                    pt_to_px: float = PT_TO_PX, stroke_px: int = 2,
                    overshoot_m: float = DRAWN_WALL_OVERSHOOT_M) -> np.ndarray:
    """A fresh bool mask holding only the (overshooting) drawn wall."""
    (x1, y1), (x2, y2) = extended_endpoints_px(
        correction, px_per_m, pt_to_px, overshoot_m)
    canvas = np.zeros(shape, np.uint8)
    cv2.line(canvas, (int(round(x1)), int(round(y1))),
             (int(round(x2)), int(round(y2))), 1, thickness=max(1, int(stroke_px)))
    return canvas.astype(bool)


def apply_drawn_wall(wall_mask: np.ndarray, correction,
                     px_per_m: float = 50.0, pt_to_px: float = PT_TO_PX,
                     stroke_px: int = 2,
                     overshoot_m: float = DRAWN_WALL_OVERSHOOT_M) -> np.ndarray:
    """``wall_mask`` plus the drawn wall, as a new bool mask.

    The result is the barrier/wall mask to hand to
    ``geometry.segment_seeded`` or ``geometry.segment_rooms`` on re-cut,
    which then produce two rooms where there was one.  The input is not
    mutated.
    """
    wall = np.asarray(wall_mask, bool)
    return wall | drawn_wall_mask(wall.shape, correction, px_per_m,
                                  pt_to_px, stroke_px, overshoot_m)


def split_mask_by_wall(mask: np.ndarray, wall_mask: np.ndarray) -> list[np.ndarray]:
    """The connected pieces of ``mask`` once ``wall_mask`` cuts it, largest first."""
    remaining = np.asarray(mask, bool) & ~np.asarray(wall_mask, bool)
    n, labels = cv2.connectedComponents(remaining.astype(np.uint8))
    pieces = [labels == i for i in range(1, n) if (labels == i).any()]
    pieces.sort(key=lambda m: int(m.sum()), reverse=True)
    return pieces


# --- rebuilding MeasuredRoom ------------------------------------------------------------


def _corrected(room: MeasuredRoom, outline_source: str, **overrides) -> CorrectedRoom:
    values = dict(name=room.name, room_type=room.room_type,
                  type_source=room.type_source, area_m2=room.area_m2,
                  written_area_m2=room.written_area_m2,
                  polygon_px=room.polygon_px, polygon_m=room.polygon_m,
                  circle_m=room.circle_m, circle_px=room.circle_px,
                  warnings=list(room.warnings), outline_source=outline_source)
    values.update(overrides)
    return CorrectedRoom(**values)


def with_outline_source(room: MeasuredRoom, outline_source: str) -> CorrectedRoom:
    """A copy of ``room`` carrying ``outline_source`` provenance."""
    if outline_source not in OUTLINE_SOURCES:
        raise ValueError(f"outline_source must be one of {OUTLINE_SOURCES}, got {outline_source!r}")
    return _corrected(room, outline_source)


def outline_source_of(room) -> str:
    """A room's outline provenance, ``"auto"`` when no correction touched it."""
    return getattr(room, "outline_source", "auto")


def room_from_mask(mask: np.ndarray, px_per_m: float, to_plan: float = 1.0,
                   outline_source: str = "auto", name: str = "",
                   room_type: str = "other", type_source: str = "none",
                   written_area_m2: float | None = None,
                   blocked: np.ndarray | None = None,
                   warnings=None) -> CorrectedRoom:
    """A ``MeasuredRoom`` measured from ``mask``, with outline provenance."""
    if outline_source not in OUTLINE_SOURCES:
        raise ValueError(f"outline_source must be one of {OUTLINE_SOURCES}, got {outline_source!r}")
    polygon_px, polygon_m, area_m2, circle_m, circle_px = _measure(
        mask, px_per_m, to_plan, blocked)
    return CorrectedRoom(
        name=name, room_type=room_type, type_source=type_source,
        area_m2=round(area_m2, 2), written_area_m2=written_area_m2,
        polygon_px=polygon_px, polygon_m=polygon_m,
        circle_m=round(circle_m, 2),
        circle_px=(round(circle_px[0], 1), round(circle_px[1], 1)),
        warnings=list(warnings or []), outline_source=outline_source)


def rebuild_room(room: MeasuredRoom, mask: np.ndarray, px_per_m: float,
                 to_plan: float = 1.0, outline_source: str = "auto",
                 blocked: np.ndarray | None = None) -> CorrectedRoom:
    """``room`` re-measured from a corrected ``mask``.

    Name, type and its source, the written area and warnings are kept;
    area, outline and largest circle are recomputed, and the room is
    marked with the correction's ``outline_source``.
    """
    if outline_source not in OUTLINE_SOURCES:
        raise ValueError(f"outline_source must be one of {OUTLINE_SOURCES}, got {outline_source!r}")
    polygon_px, polygon_m, area_m2, circle_m, circle_px = _measure(
        mask, px_per_m, to_plan, blocked)
    return _corrected(room, outline_source, area_m2=round(area_m2, 2),
                      polygon_px=polygon_px, polygon_m=polygon_m,
                      circle_m=round(circle_m, 2),
                      circle_px=(round(circle_px[0], 1), round(circle_px[1], 1)))


def merge_measured_rooms(target: MeasuredRoom, region: MeasuredRoom,
                         target_mask: np.ndarray, region_mask: np.ndarray,
                         px_per_m: float, to_plan: float = 1.0,
                         blocked: np.ndarray | None = None) -> MeasuredRoom:
    """The target room after merging: its identity, the union's measures."""
    result = merge_masks(target_mask, region_mask, px_per_m, to_plan, blocked)
    return rebuild_room(target, result.mask, px_per_m, to_plan,
                        outline_source="merged", blocked=blocked)


# --- replay ---------------------------------------------------------------------------


@dataclass(eq=False)
class ReplayResult:
    """The outcome of replaying stored corrections."""

    masks: list
    wall_mask: np.ndarray | None = None
    outline_sources: list = field(default_factory=list)
    results: list = field(default_factory=list)  # MergeResult per Merge, in order

    @property
    def barrier_mask(self) -> np.ndarray | None:
        return self.wall_mask


def apply_corrections(masks, corrections, px_per_m: float,
                      pt_to_px: float = PT_TO_PX, to_plan: float = 1.0,
                      wall_mask: np.ndarray | None = None,
                      blocked: np.ndarray | None = None) -> ReplayResult:
    """Replay stored corrections over room masks (and a wall mask).

    Merges union their region into their target and drop the region's own
    mask; drawn walls accumulate into the returned wall mask, ready for
    ``geometry.segment_seeded`` / ``segment_rooms`` to split on re-cut.
    Order is the stored order, so replay is deterministic: applying the
    same corrections (including after a JSON round-trip) to the same
    inputs gives identical masks and ``outline_sources``.
    """
    if isinstance(corrections, (str, bytes)):
        corrections = corrections_from_json(corrections)
    corrections = [correction_from_dict(c) if isinstance(c, dict) else c
                   for c in corrections]
    out = [np.array(m, bool) for m in masks]
    sources = ["auto"] * len(out)
    wall = None if wall_mask is None else np.array(wall_mask, bool)
    results: list = []
    for correction in corrections:
        if isinstance(correction, Merge):
            result = apply_merge(out, correction, px_per_m, pt_to_px,
                                 to_plan, blocked)
            results.append(result)
            out[result.target_index] = result.mask
            sources[result.target_index] = "merged"
            if result.merged_index != result.target_index:
                del out[result.merged_index]
                del sources[result.merged_index]
        elif isinstance(correction, DrawnWall):
            base = wall if wall is not None else (
                np.zeros_like(out[0]) if out else None)
            if base is None:
                raise ValueError("A drawn wall needs a wall mask or room masks for its shape")
            wall = apply_drawn_wall(base, correction, px_per_m, pt_to_px)
        else:
            raise TypeError(f"Not a correction: {correction!r}")
    return ReplayResult(masks=out, wall_mask=wall,
                        outline_sources=sources, results=results)


# Replay is the stored-corrections entry point; both names read naturally.
replay_corrections = apply_corrections
