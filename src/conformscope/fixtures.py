"""Fixtures: what is built into a plan and a wheelchair cannot stand on (CONTEXT.md).

The geometry core already finds them on a vector PDF -- placards by their crossed box,
appliances as small closed cells, toilets as one rounded symbol -- but only as pixels that
block the turning circle. Here each one becomes an object: its kind, its outline and the
room it stands in. An appliance standing in a bathroom or a WC is a washbasin.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

SANITARY = {"wc", "bathroom"}
MIN_FIXTURE_PX = 20   # fewer pixels than this is a speck left over, not a fixture
OVERLAP_PX = 5        # how far one detector's fixture claims the strokes around it


@dataclass
class FixtureMask:
    """A fixture on the grid the walls were rasterised on."""
    kind: str                 # "placard" | "appliance" | "washbasin" | "toilet"
    origin: tuple[int, int]   # where `crop` sits on the grid
    crop: np.ndarray
    room: int | None = None   # index of the room it stands in

    def full_mask(self, shape) -> np.ndarray:
        mask = np.zeros(shape, bool)
        x, y = self.origin
        h, w = self.crop.shape
        mask[y:y + h, x:x + w] = self.crop
        return mask


@dataclass
class MeasuredFixture:
    kind: str
    room: int | None
    polygon_px: list[tuple[float, float]]  # on the plan image
    polygon_m: list[tuple[float, float]]   # from the plan's top-left corner, y down
    outline_source: str = "vector"         # "vector" | "muse" | "sam"
    space: dict | None = None              # the transfer or washbasin space, issue #8
    warnings: list[str] = field(default_factory=list)


def _components(mask: np.ndarray, kind: str) -> list[FixtureMask]:
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < MIN_FIXTURE_PX:
            continue
        out.append(FixtureMask(kind, (int(x), int(y)), labels[y:y + h, x:x + w] == i))
    return out


def split_fixtures(placards: np.ndarray, cells: np.ndarray, toilets: np.ndarray) -> list[FixtureMask]:
    """One fixture per symbol from the three detectors' masks.

    The cell finder also closes a box around a toilet or a placard, so a cell keeps only
    what neither of them already holds.
    """
    kernel = np.ones((2 * OVERLAP_PX + 1, 2 * OVERLAP_PX + 1), np.uint8)
    taken = cv2.dilate((placards | toilets).astype(np.uint8), kernel).astype(bool)
    return (_components(placards, "placard") + _components(toilets, "toilet")
            + _components(cells & ~taken, "appliance"))


def assign_rooms(fixtures: list[FixtureMask], room_masks: list[np.ndarray],
                 room_types: list[str]) -> None:
    """Put each fixture in the room holding most of it; an appliance there in a bathroom
    or a WC is a washbasin."""
    for fixture in fixtures:
        x, y = fixture.origin
        h, w = fixture.crop.shape
        overlaps = [int((mask[y:y + h, x:x + w] & fixture.crop).sum()) for mask in room_masks]
        if not overlaps or max(overlaps) == 0:
            continue
        fixture.room = int(np.argmax(overlaps))
        if fixture.kind == "appliance" and room_types[fixture.room] in SANITARY:
            fixture.kind = "washbasin"
