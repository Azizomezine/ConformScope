"""The free floor a wheelchair parks on beside a toilet or in front of a washbasin.

A **transfer space** is a free 0.80 x 1.30 m rectangle touching a toilet; a **washbasin
space** the same rectangle touching the front of a washbasin (CONTEXT.md). Both are read
leniently: anywhere in the fixture's room, in either orientation, and a door swing may
cross them -- only walls and fixtures may not. The rule in the arrêté du 24 décembre 2015
is stricter (beside the toilet, outside the door swing), so a pass says the space was
found, never that the room complies. The washbasin space's source is still to confirm.

Every placement is tried at once: an integral image counts the blocked and the touching
pixels under each window, so the search is exact on the grid, not sampled.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import cv2
import numpy as np

from conformscope.fixtures import FixtureMask

SHORT_M = 0.80
LONG_M = 1.30
TOUCH_M = 0.05   # a rectangle this close to the fixture touches it
KINDS = {"toilet": "transfer", "washbasin": "washbasin"}


@dataclass
class SpaceFit:
    kind: str                                  # "transfer" | "washbasin"
    fits: bool
    rect: tuple[int, int, int, int] | None     # x, y, w, h on the grid; the best attempt if it does not fit

    @property
    def to_confirm(self) -> bool:
        return self.kind == "washbasin"

    @property
    def verdict(self) -> str:
        if self.kind == "transfer":
            return ("Transfer space found" if self.fits
                    else "No 0.80 × 1.30 m transfer space beside this toilet")
        return ("Washbasin space found (rule to confirm)" if self.fits
                else "No 0.80 × 1.30 m space in front of this washbasin (rule to confirm)")


def _window_sums(mask: np.ndarray, h: int, w: int) -> np.ndarray:
    """How many pixels of `mask` each h x w window holds, indexed by its top-left corner."""
    ii = np.pad(mask.astype(np.int32).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    return ii[h:, w:] - ii[:-h, w:] - ii[h:, :-w] + ii[:-h, :-w]


def find_space(free: np.ndarray, touch: np.ndarray, short_px: int,
               long_px: int) -> tuple[bool, tuple[int, int, int, int]] | None:
    """A short x long rectangle of free pixels holding at least one `touch` pixel.

    Returns (True, rect) for a fit, else (False, rect) for the touching placement with the
    fewest blocked pixels; None when nothing can touch at all.
    """
    best = None  # (blocked, -touched, rect)
    for h, w in {(long_px, short_px), (short_px, long_px)}:
        if h > free.shape[0] or w > free.shape[1]:
            continue
        touched = _window_sums(touch, h, w)
        blocked = np.where(touched > 0, _window_sums(~free, h, w), np.iinfo(np.int32).max)
        y, x = np.unravel_index(np.argmin(blocked), blocked.shape)
        if touched[y, x] == 0:
            continue
        candidate = (int(blocked[y, x]), -int(touched[y, x]), (int(x), int(y), w, h))
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    if best is None:
        return None
    return best[0] == 0, best[2]


def front_touch(fixture: FixtureMask, free: np.ndarray, depth_px: int,
                probe_px: int | None = None) -> np.ndarray:
    """The free strip along the fixture's front: of its four sides, the one facing the
    most free floor within `probe_px`."""
    x0, y0 = fixture.origin
    h, w = fixture.crop.shape
    x1, y1 = x0 + w, y0 + h
    probe = probe_px or depth_px
    H, W = free.shape
    sides = [  # (strip, band) as (y slice, x slice)
        ((slice(max(0, y0 - depth_px), y0), slice(x0, x1)), (slice(max(0, y0 - probe), y0), slice(x0, x1))),
        ((slice(y1, min(H, y1 + depth_px)), slice(x0, x1)), (slice(y1, min(H, y1 + probe)), slice(x0, x1))),
        ((slice(y0, y1), slice(max(0, x0 - depth_px), x0)), (slice(y0, y1), slice(max(0, x0 - probe), x0))),
        ((slice(y0, y1), slice(x1, min(W, x1 + depth_px))), (slice(y0, y1), slice(x1, min(W, x1 + probe)))),
    ]
    strip, _ = max(sides, key=lambda side: int(free[side[1]].sum()))
    touch = np.zeros_like(free)
    touch[strip] = free[strip]
    return touch


def check_spaces(fixtures: list[FixtureMask], room_masks: list[np.ndarray], walls: np.ndarray,
                 px_per_m: float) -> list[SpaceFit | None]:
    """The space each toilet and washbasin needs, None for every other fixture.

    `walls` is everything that bounds the floor; door swings are deliberately not in it.
    """
    taken = np.zeros(walls.shape, bool)
    for fixture in fixtures:
        taken |= fixture.full_mask(walls.shape)
    short_px, long_px = round(SHORT_M * px_per_m), round(LONG_M * px_per_m)
    touch_px = max(1, round(TOUCH_M * px_per_m))
    ring = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * touch_px + 1, 2 * touch_px + 1))

    out: list[SpaceFit | None] = []
    for fixture in fixtures:
        kind = KINDS.get(fixture.kind)
        if kind is None or fixture.room is None:
            out.append(None)
            continue
        room = room_masks[fixture.room]
        ys, xs = np.nonzero(room)
        cx0, cy0 = max(0, int(xs.min()) - touch_px), max(0, int(ys.min()) - touch_px)
        cx1, cy1 = int(xs.max()) + touch_px + 1, int(ys.max()) + touch_px + 1
        window = (slice(cy0, cy1), slice(cx0, cx1))
        free = room[window] & ~walls[window] & ~taken[window]
        local = replace(fixture, origin=(fixture.origin[0] - cx0, fixture.origin[1] - cy0))
        if kind == "transfer":
            own = local.full_mask(free.shape)
            touch = cv2.dilate(own.astype(np.uint8), ring).astype(bool) & free
        else:
            touch = front_touch(local, free, touch_px, short_px)
        # Padded so a room too small for the rectangle still shows the best attempt,
        # standing partly outside it.
        found = find_space(np.pad(free, long_px), np.pad(touch, long_px), short_px, long_px)
        if found is None:
            out.append(SpaceFit(kind, False, None))
            continue
        fits, (x, y, w, h) = found
        out.append(SpaceFit(kind, fits, (x + cx0 - long_px, y + cy0 - long_px, w, h)))
    return out


def accessible_wc(spaces: list[SpaceFit | None]) -> bool | None:
    """Whether the home has a WC whose toilet has a transfer space; None with no toilet."""
    transfers = [space for space in spaces if space is not None and space.kind == "transfer"]
    if not transfers:
        return None
    return any(space.fits for space in transfers)


def wcs_without_toilet(room_types: list[str], fixtures: list[FixtureMask]) -> list[int]:
    """The rooms typed as a WC with no toilet found in them."""
    with_toilet = {f.room for f in fixtures if f.kind == "toilet"}
    return [i for i, room_type in enumerate(room_types) if room_type == "wc" and i not in with_toilet]


def space_body(fit: SpaceFit, px_per_m: float, to_plan: float) -> dict:
    """A space as the API returns it: its verdict and its rectangle on the plan and in metres."""
    corners = []
    if fit.rect is not None:
        x, y, w, h = fit.rect
        corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    return {"kind": fit.kind, "fits": fit.fits, "verdict": fit.verdict, "to_confirm": fit.to_confirm,
            "polygon_px": [(round(cx * to_plan, 1), round(cy * to_plan, 1)) for cx, cy in corners],
            "polygon_m": [(round(cx / px_per_m, 3), round(cy / px_per_m, 3)) for cx, cy in corners]}
