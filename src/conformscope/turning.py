"""Turning circle check: the Ø1.50 m circle a wheelchair needs to turn.

Approach: rasterisation. The room polygon (in metres, from the plan's
top-left corner, y down) is filled onto a fine grid at ``PX_PER_M`` pixels
per metre inside its own bounding box, and the largest empty circle is the
peak of the distance transform over that mask — the same measure
``geometry._fit_circle`` gives the rooms pipeline, so both agree on what
"largest circle" means. A grid search (polylabel-style) was not used: the
distance transform finds the big lobe of an asymmetric room such as an L
exactly, where a centroid-seeded search can settle in the corridor.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from conformscope.geometry import _fit_circle

PX_PER_M = 200  # grid the polygon is rasterised on, pixels per metre
MIN_DIAMETER_M = 1.50


@dataclass(frozen=True)
class TurningCheck:
    conforme: bool
    max_diameter_m: float
    center_m: tuple[float, float] | None

    @property
    def verdict(self) -> str:
        """The PMR verdict in words, as it is shown on a plan."""
        if self.conforme:
            return "Conforme PMR"
        return f"Non conforme PMR (max Ø{self.max_diameter_m:.2f} m)"


def _clean(polygon_m) -> list[tuple[float, float]]:
    """The outline's points as floats, with no repeated closing vertex."""
    points = [(float(x), float(y)) for x, y in polygon_m]
    while len(points) > 1 and points[-1] == points[0]:
        points.pop()
    cleaned: list[tuple[float, float]] = []
    for point in points:
        if not cleaned or point != cleaned[-1]:
            cleaned.append(point)
    while len(cleaned) > 1 and cleaned[-1] == cleaned[0]:
        cleaned.pop()
    return cleaned


def _area_m2(points: list[tuple[float, float]]) -> float:
    return abs(sum(x1 * y2 - x2 * y1
                   for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]))) / 2


def check_turning(polygon_m, min_diameter_m: float = MIN_DIAMETER_M) -> TurningCheck:
    """Largest inscribed circle in a room polygon given in metres.

    `polygon_m` is a closed outline from the plan's top-left corner, y down
    (``rooms.MeasuredRoom.polygon_m``), possibly repeating its first vertex
    at the end. Degenerate outlines — fewer than three distinct points, or
    zero area — hold no circle and come back non-conforme, never a crash.
    """
    degenerate = TurningCheck(conforme=False, max_diameter_m=0.0, center_m=None)
    if polygon_m is None:
        return degenerate
    try:
        points = _clean(polygon_m)
    except (TypeError, ValueError):
        return degenerate
    if len(set(points)) < 3 or _area_m2(points) <= 1e-12:
        return degenerate

    min_x = min(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_x = max(x for x, _ in points)
    max_y = max(y for _, y in points)
    width_m, height_m = max_x - min_x, max_y - min_y
    if width_m <= 0 or height_m <= 0:
        return degenerate

    width = int(math.ceil(width_m * PX_PER_M)) + 1
    height = int(math.ceil(height_m * PX_PER_M)) + 1
    pixels = np.array(
        [[round((x - min_x) * PX_PER_M), round((y - min_y) * PX_PER_M)]
         for x, y in points],
        dtype=np.int32,
    )
    mask = np.zeros((height, width), np.uint8)
    cv2.fillPoly(mask, [pixels], 1)
    if not mask.any():
        return degenerate

    radius_m, (cx, cy) = _fit_circle(mask.astype(bool), (0, 0, width - 1, height - 1),
                                     float(PX_PER_M))
    diameter_m = 2 * radius_m
    if diameter_m <= 0:
        return degenerate
    center_m = (round(min_x + cx / PX_PER_M, 3), round(min_y + cy / PX_PER_M, 3))
    return TurningCheck(
        conforme=diameter_m >= min_diameter_m,
        max_diameter_m=round(float(diameter_m), 3),
        center_m=center_m,
    )
