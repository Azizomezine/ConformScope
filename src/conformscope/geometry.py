"""Occupancy map, room segmentation and the distance-transform circle check."""
from __future__ import annotations

from dataclasses import InitVar, dataclass, field

import cv2
import numpy as np

DOOR_CLOSE_M = 0.65   # wall dilation radius to seal door/window openings
# Unclaimed floor a sealed doorway bounds is a dégagement down to this size --
# below MIN_ROOM_M2, since a landing between three doors is smaller than any
# room yet is one (the 0,91 m couloir of Logement A, 1.12 m²).
MIN_COULOIR_M2 = 1.0
MIN_ROOM_M2 = 1.5     # ignore slivers smaller than this -- raised from 1.0
                      # (2026-09-20): both phantom rooms an auditor flagged on
                      # samples/Plan_Logement_Niveau_02.pdf were 1.01 m² and
                      # 1.45 m², wall-thickness/noise slivers the old floor let
                      # through. 1.5 clears both and still sits under the
                      # smallest real room on that same plan (1.56 m²) -- a
                      # thin margin, worth widening once a second plan's
                      # fixture confirms it holds.

# The **building outline** (CONTEXT.md): only floor inside it is a room. It is
# grown from the wall mass, and wall masses closer than twice BUILDING_GAP_M
# are one building -- enough to bridge a bay a facade leaves open in its poché
# (4 m), short of the 4.7 m between PLAN APPARTEMENT's plan and its site-plan
# inset at the sheet's true 1/50. Freeda R+4 has its poché in some hundred
# fragments and its facade drawn as lines: 2 m makes it one building whether
# it is read at its true 1/50 or at the 1:100 the calibration still assumes,
# where 1.5 m holds only at 1/50 and leaves it in four at 1:100.
BUILDING_GAP_M = 2.0
# The outline reaches this far past the hull of the wall mass, for the rooms
# along a facade drawn in lines rather than poché: Freeda's corner rooms lie
# beyond its last filled wall.
BUILDING_MARGIN_M = 1.0
# A second wing counts when its extent is at least this share of the largest;
# a site-plan inset's footprints are a few percent (4 m² against 59 m² on
# PLAN APPARTEMENT).
WING_MIN_SHARE = 1 / 3
# The grid the outline is worked out on: a closing as wide as BUILDING_GAP_M
# costs seconds at full resolution on an A0 sheet, and the outline only has to
# say which side of it most of a room's floor lies.
OUTLINE_CELL_M = 0.1


@dataclass
class Room:
    number: int
    # bool, room interior (eroded near walls), page-sized as given. Kept only
    # as `crop` -- the mask over the room's own extent, from `origin` -- since
    # a page-sized mask per room is ~35 MB on an A0 sheet, and a level of ~350
    # rooms then held ~12 GB. `mask` rebuilds the page-sized array on request;
    # a point test is `contains`, which builds nothing.
    mask: InitVar[np.ndarray]
    area_m2: float
    bbox: tuple               # x0, y0, x1, y1 in px
    max_clearance_m: float    # largest fitting circle radius, meters
    best_center: tuple        # (x, y) px of max clearance -- what gets drawn
    fixture_density: float    # obstacle px fraction inside room bbox
    name: str = ""
    apartment: str = ""       # "Logement A", "Communs", ...
    room_type: str = "inconnu"        # set by roomtype.resolve()
    provenance: str | None = None     # "text" | "ai" | "human" -- of the type
    # Whose authority says this room exists at all: "ai" when it grew from a
    # seed (docs/adr/0023), None when the walls alone cut it out.
    existence: str | None = None
    phantom: bool = False             # set by contest.replay_phantoms()
    anchor_center: tuple | None = None  # best_center as segment_rooms first found
                                        # it -- see anchor_pt()
    crop: np.ndarray = field(init=False, repr=False, compare=False)
    origin: tuple = field(init=False, repr=False)   # (x, y) px of crop[0, 0]
    shape: tuple = field(init=False, repr=False)    # the page's (h, w) in px

    def __post_init__(self, mask: np.ndarray) -> None:
        if self.anchor_center is None:
            self.anchor_center = self.best_center
        self.shape = mask.shape
        ys, xs = np.nonzero(mask)
        if len(xs) == 0:
            self.origin, self.crop = (0, 0), np.zeros((0, 0), bool)
            return
        x0, y0 = int(xs.min()), int(ys.min())
        self.origin = (x0, y0)
        self.crop = mask[y0:int(ys.max()) + 1, x0:int(xs.max()) + 1].copy()

    def full_mask(self) -> np.ndarray:
        """The page-sized mask, built afresh: hold it no longer than needed."""
        out = np.zeros(self.shape, bool)
        x0, y0 = self.origin
        h, w = self.crop.shape
        out[y0:y0 + h, x0:x0 + w] = self.crop
        return out

    def contains(self, x: int, y: int) -> bool:
        """Whether pixel (x, y) of the page is inside the room."""
        cx, cy = x - self.origin[0], y - self.origin[1]
        h, w = self.crop.shape
        return 0 <= cy < h and 0 <= cx < w and bool(self.crop[cy, cx])

    def fits(self, diameter_m: float) -> bool:
        return self.max_clearance_m >= diameter_m / 2

    def anchor_pt(self, px_to_pt: float) -> tuple[float, float]:
        """`anchor_center` in PDF points -- this room's stable identity (D4).

        `number` is a connected-component id that reshuffles on every
        re-segmentation, so nothing may be persisted against it. The
        max-clearance point segment_rooms first computes is a property of the
        physical space, so a stored human correction can find its way back to
        the same room after the pipeline re-runs. It must stay fixed even
        when a later, type-gated pass (pipeline._promote_sanitary_obstacles)
        moves `best_center` to a smaller circle once dashed fixtures are
        excluded -- otherwise the anchor a client already holds would stop
        matching the moment a room's type (and so whether that pass runs)
        changes. `px_to_pt` is 72/dpi.
        """
        return (self.anchor_center[0] * px_to_pt, self.anchor_center[1] * px_to_pt)


# Set after the class: inside it, `mask` is the dataclass's init argument.
Room.mask = property(Room.full_mask)


def _disk(radius_px: int) -> np.ndarray:
    r = max(1, radius_px)
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def _grow_along(labels: np.ndarray, allowed: np.ndarray, steps: int) -> np.ndarray:
    """Grow each label into unlabelled `allowed` pixels, one pixel a step --
    a distance measured along the floor, so it never crosses a wall."""
    lab = labels.astype(np.float32)
    kernel = np.ones((3, 3), np.uint8)
    for _ in range(steps):
        open_ = (lab == 0) & allowed
        if not open_.any():
            break
        lab = np.where(open_, cv2.dilate(lab, kernel), lab)
    return lab.astype(np.int32)


def _adopt_couloirs(labels: np.ndarray, floor: np.ndarray, px_per_m: float,
                    doors: np.ndarray | None = None) -> tuple[np.ndarray, set]:
    """Give a room to enclosed floor no room reclaimed.

    The doorway seal closes any gap under 2 x DOOR_CLOSE_M, so a couloir that
    narrow leaves no seed of its own: its floor comes back unclaimed. Such
    floor is a room. Where the couloir widens past the seal -- in front of a
    door recess -- a seed survives there as a piece of it; a piece smaller than
    the unclaimed floor it opens onto, with no wall or door between them, is
    that couloir widening and joins it.
    """
    labels = labels.copy()
    ids, counts = np.unique(labels, return_counts=True)
    slivers = ids[(ids != 0) & (counts / px_per_m ** 2 < MIN_ROOM_M2)]
    if len(slivers):
        labels[np.isin(labels, slivers)] = 0    # a sliver gives its floor back
    area = {int(i): int(c) for i, c in zip(*np.unique(labels, return_counts=True))}
    unclaimed = (floor & (labels == 0)).astype(np.uint8)
    n, comp, stats, _ = cv2.connectedComponentsWithStats(unclaimed)
    h, w = labels.shape
    parent: dict = {}

    def root(x):
        while parent.get(x, x) != x:
            x = parent[x]
        return x

    pieces = {}
    for c in range(1, n):
        x, y, cw, ch, size = stats[c]
        if x == 0 or y == 0 or x + cw == w or y + ch == h:
            continue                    # reaches the page edge: outdoors
        y0, y1, x0, x1 = max(y - 1, 0), min(y + ch + 1, h), max(x - 1, 0), min(x + cw + 1, w)
        own = comp[y0:y1, x0:x1] == c
        pieces[c] = (y0, x0, own)
        rim = (cv2.dilate(own.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
               & floor[y0:y1, x0:x1] & ~own)
        for lab in np.unique(labels[y0:y1, x0:x1][rim]):
            if lab and area[int(lab)] < size:
                parent[root(("room", int(lab)))] = root(("floor", c))
    groups: dict = {}
    for c in pieces:
        groups.setdefault(root(("floor", c)), []).append(c)
    for lab in area:
        if lab and root(("room", lab)) != ("room", lab):
            groups.setdefault(root(("room", lab)), []).append(("room", lab))
    def box(m) -> tuple[int, int, int, int]:
        """The member's bounding box, (y0, y1, x0, x1) with exclusive ends."""
        if isinstance(m, tuple):
            ys, xs = np.nonzero(labels == m[1])
            return int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1
        y0, x0, own = pieces[m]
        return y0, y0 + own.shape[0], x0, x0 + own.shape[1]

    nxt = int(labels.max()) + 1
    small: set = set()
    for members in groups.values():
        # Worked inside the group's own box, one pixel wider so a doorway it
        # touches is in view: a page holds thousands of these, and a full-page
        # mask for each one is minutes on a large sheet.
        boxes = [box(m) for m in members]
        y0, y1 = max(min(b[0] for b in boxes) - 1, 0), min(max(b[1] for b in boxes) + 1, h)
        x0, x1 = max(min(b[2] for b in boxes) - 1, 0), min(max(b[3] for b in boxes) + 1, w)
        sub = labels[y0:y1, x0:x1]
        whole = np.zeros(sub.shape, bool)
        for m in members:
            if isinstance(m, tuple):
                whole |= sub == m[1]
            else:
                py, px, own = pieces[m]
                whole[py - y0:py - y0 + own.shape[0], px - x0:px - x0 + own.shape[1]] |= own
        area_m2 = whole.sum() / px_per_m ** 2
        if area_m2 < MIN_ROOM_M2:
            # A dégagement between doors can be smaller than any room: kept
            # if a sealed doorway bounds it, never if only walls do.
            touches_door = doors is not None and (cv2.dilate(
                whole.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
                & doors[y0:y1, x0:x1]).any()
            if area_m2 < MIN_COULOIR_M2 or not touches_door:
                continue
            small.add(nxt)
        sub[whole] = nxt
        nxt += 1
    return labels, small


def _fit_circle(mask: np.ndarray, bbox: tuple, px_per_m: float) -> tuple[float, tuple]:
    """Largest inscribed circle in `mask` (a room's own free space), by a
    per-room distance transform. `bbox` crops the search to the room, and its
    own boundary blocks the transform like a wall would.

    Shared by segment_rooms (first pass, room's own obstacle_mask already
    carved out) and refit_with_extra_obstacles (second pass, a sanitary
    room's promoted dashed fixtures carved out too) so both fits agree on
    what "largest circle" means.

    Returns (max_clearance_m, best_center) where best_center is (x, y) px in
    full-canvas coordinates.
    """
    x0, y0, x1, y1 = bbox
    sub = mask[y0:y1 + 1, x0:x1 + 1]
    pad = np.pad(sub, 1).astype(np.uint8)  # room boundary blocks
    d = cv2.distanceTransform(pad, cv2.DIST_L2, 5)[1:-1, 1:-1]
    d_max = float(d.max())
    # Among near-maximal points, prefer the one closest to the room
    # centroid: raw argmax tends to hug furniture corners.
    cand_y, cand_x = np.nonzero(d >= d_max - 0.02 * px_per_m)
    cy_c, cx_c = cand_y.mean(), cand_x.mean()
    i = int(np.argmin((cand_y - cy_c) ** 2 + (cand_x - cx_c) ** 2))
    best = (int(cand_y[i]) + y0, int(cand_x[i]) + x0)
    return d_max / px_per_m, (int(best[1]), int(best[0]))


def refit_with_extra_obstacles(room: "Room", extra_obstacle_mask: np.ndarray,
                               obstacle_mask: np.ndarray, px_per_m: float) -> None:
    """Recompute one room's circle after excluding newly-promoted fixtures.

    Used for a sanitary room once dashed equipment (a toilet, a washing
    machine) has been identified inside it (pipeline._promote_sanitary_obstacles):
    the room's boundary hasn't moved, so there's no need to re-segment --
    only its circle fit changes.

    `room.mask` itself is deliberately left untouched: it is the room's
    identity surface (labels.room_at_point tests a stored anchor against it,
    D4), and the point a *previous*, un-promoted fit chose as this very
    room's own anchor can legitimately sit where a fixture turns out to be --
    carving that pixel out of `room.mask` here would orphan the room's own
    anchor the moment its type makes this pass run. Only a temporary working
    mask feeds the circle fit.
    """
    working = room.mask & ~extra_obstacle_mask
    room.max_clearance_m, room.best_center = _fit_circle(working, room.bbox, px_per_m)
    x0, y0, x1, y1 = room.bbox
    merged = obstacle_mask | extra_obstacle_mask
    room.fixture_density = float(merged[y0:y1 + 1, x0:x1 + 1].mean())


def building_outline(wall_mask: np.ndarray, px_per_m: float) -> np.ndarray | None:
    """The **building outline**: where on the page a room may be, or None
    when there is no wall mass to tell (every candidate then stands).

    Built from the filled walls alone, never the stroked lines: the frame,
    the cartouche and the legend are lines, and so is everything that boxes a
    piece of sheet furniture in. Wall masses within 2 x BUILDING_GAP_M of one
    another are one building; a building's extent is the convex hull of its
    mass, BUILDING_MARGIN_M wider. The largest is the building, and any other
    at least WING_MIN_SHARE of it a second wing -- never a site-plan inset's
    footprints. A hull rather than the poché's own holes, because a facade
    drawn in lines leaves the poché open: Freeda's would enclose nothing.
    """
    if not wall_mask.any():
        return None
    step = max(1, int(OUTLINE_CELL_M * px_per_m))
    h, w = wall_mask.shape
    gh, gw = -(-h // step), -(-w // step)
    padded = np.zeros((gh * step, gw * step), bool)
    padded[:h, :w] = wall_mask
    # A cell holds wall if any pixel in it does: a hairline of poché counts.
    coarse = padded.reshape(gh, step, gw, step).any(axis=(1, 3)).astype(np.uint8)
    cell_per_m = px_per_m / step
    closed = cv2.morphologyEx(coarse, cv2.MORPH_CLOSE,
                              _disk(int(BUILDING_GAP_M * cell_per_m)))
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    hulls = [cv2.convexHull(c) for c in contours]
    areas = [cv2.contourArea(hull) for hull in hulls]
    largest = max(areas)
    outline = np.zeros_like(coarse)
    cv2.fillPoly(outline, [hull for hull, a in zip(hulls, areas)
                           if a >= WING_MIN_SHARE * largest], 1)
    outline = cv2.dilate(outline, _disk(int(BUILDING_MARGIN_M * cell_per_m)))
    full = np.repeat(np.repeat(outline.astype(bool), step, axis=0), step, axis=1)
    return full[:h, :w]


def segment_rooms(wall_mask: np.ndarray, barrier_mask: np.ndarray,
                  obstacle_mask: np.ndarray,
                  px_per_m: float,
                  door_mask: np.ndarray | None = None,
                  fixture_mask: np.ndarray | None = None,
                  ) -> tuple[np.ndarray, np.ndarray, list[Room]]:
    """Returns (free_space, dist_map_px, rooms).

    wall_mask: filled structure; barrier_mask: stroked partition lines
    (space-dividing, also physical); obstacle_mask: fixtures (block the
    circle but do not divide rooms); door_mask: detected door-swing
    bboxes (extract.door_seal_mask) -- sealed for room *separation* only,
    not subtracted from the circle-fitting free space, so a doorway's
    floor stays usable for the Ø1.50 circle.

    fixture_mask: appliances and toilets (docs/adr/0014, 0015). Carved from each
    room's floor and circle exactly as obstacle_mask is, but *not* counted
    when deciding whether a component is a sliver: a fixture stands in a
    room, and a WC compartment is a room however much of it the toilet takes. A
    placard stays in obstacle_mask on purpose -- it *is* its component, and
    ADR-0012 relies on its fill taking that component under MIN_ROOM_M2.
    """
    # Seal door/window openings so each room becomes its own component.
    # Doors with a detected arc are sealed precisely via door_mask; the
    # dilation below is the fallback for doorways with no detected arc.
    solid = (wall_mask | barrier_mask).astype(np.uint8)
    if door_mask is not None:
        solid = solid | door_mask.astype(np.uint8)
    sealed = cv2.dilate(solid, _disk(int(DOOR_CLOSE_M * px_per_m)))
    open_space = (sealed == 0).astype(np.uint8)
    n, labels = cv2.connectedComponents(open_space)

    # Everything reachable from the page border is "outside".
    border_labels = set(labels[0, :]) | set(labels[-1, :]) | set(labels[:, 0]) | set(labels[:, -1])
    seeds = np.where(np.isin(labels, list(border_labels)), 0, labels).astype(np.int32)

    # Distance transform over true free space (everything solid blocks).
    before_fixtures = ~(wall_mask | barrier_mask | obstacle_mask)
    free = before_fixtures if fixture_mask is None \
        else before_fixtures & ~fixture_mask
    dist = cv2.distanceTransform(free.astype(np.uint8), cv2.DIST_L2, 5)

    # Expand seed labels back over the band the sealing dilation eroded --
    # along the floor, never through a wall or a sealed doorway, so a room
    # regrows only into space it is open to. Anything farther (e.g. the
    # outdoors) does not belong to a room.
    doors = door_mask.astype(bool) if door_mask is not None else False
    floor = before_fixtures & ~doors
    reach = int(DOOR_CLOSE_M * px_per_m + 2)
    full_labels = _grow_along(seeds, floor, reach)
    full_labels, small_couloirs = _adopt_couloirs(
        full_labels, floor, px_per_m, doors if door_mask is not None else None)
    # A sealed doorway's own floor goes to the room beside it.
    if door_mask is not None:
        full_labels = _grow_along(full_labels, before_fixtures & doors, 2)

    # A box of lines outside the building -- the frame and the margin it
    # encloses, a cartouche cell, the legend -- is no candidate at all, so it
    # is not a phantom room either: it is left out here, before any room is
    # listed. Whether a logement claims a room is not asked: a room inside the
    # building that none encloses stays, unplaced (CONTEXT.md's Logement).
    # The outline reads the filled walls only, so the corrections a search
    # tries (a line promoted to wall line, a drawn wall) never move it: a lost
    # room claimed outside it is found by no correction and stays unfulfilled.
    building = building_outline(wall_mask, px_per_m)

    def kept(lab, whole) -> bool:
        if building is not None and 2 * (whole & building).sum() < whole.sum():
            return False
        return (whole.sum() / px_per_m ** 2 >= MIN_ROOM_M2
                or lab in small_couloirs)
    rooms = _rooms(full_labels, free, obstacle_mask, fixture_mask, px_per_m, kept)
    return free, dist, rooms


def _rooms(full_labels: np.ndarray, free: np.ndarray, obstacle_mask: np.ndarray,
           fixture_mask: np.ndarray | None, px_per_m: float,
           kept=lambda lab, whole: True, existence: str | None = None) -> list[Room]:
    """One Room per label, its circle fit in its own free floor."""
    solid = obstacle_mask if fixture_mask is None else obstacle_mask | fixture_mask
    rooms = []
    for lab in np.unique(full_labels):
        if lab == 0:
            continue
        whole = full_labels == lab
        if not kept(lab, whole):
            continue
        mask = whole & free
        if not mask.any():
            continue
        area_m2 = mask.sum() / px_per_m ** 2
        ys, xs = np.nonzero(mask)
        bbox = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))
        # Per-room distance transform: the circle must fit inside this
        # room's own free space, not borrow clearance through a doorway.
        max_clear, best_center = _fit_circle(mask, bbox, px_per_m)
        sub_obst = solid[bbox[1]:bbox[3] + 1, bbox[0]:bbox[2] + 1]
        density = float(sub_obst.mean())
        rooms.append(Room(number=int(lab), mask=mask, area_m2=float(area_m2), bbox=bbox,
                          max_clearance_m=max_clear, best_center=best_center,
                          fixture_density=density, existence=existence))
    rooms.sort(key=lambda r: (r.bbox[0], r.bbox[1]))
    return rooms


# How far inside its outline a seed is shrunk, tried in turn until one leaves
# enough of a seed (SEED_MIN_PX): well inside the room first, so a loose
# outline -- about a wall thickness over, as the model draws them -- cannot
# put a seed in the neighbour; a narrow room (a couloir, a salle d'eau) only
# survives a smaller shrink.
SEED_SHRINK_M = (0.30, 0.15)
SEED_SHRINK_LAST_PX = 2
SEED_MIN_PX = 50
# How far a seed grows along the floor: past any room a seed sits in, short
# of running on for ever through a doorway nothing sealed.
SEED_REACH_M = 3.0
# Two outlines sharing more than this share of the *larger* one are one room
# seen from two overlapping crops. Of the larger, not the smaller as the
# prototype had it: a placard's outline lies wholly inside the séjour's it
# opens off, and "half of the smaller" then threw the séjour away as the
# placard seen again -- its seed went with it, and so did the room (the
# 21.93 m² pièce à vivre on Freeda R+4, the 30.9 m² séjour on Niveau 02).
SAME_ROOM_OVERLAP = 0.5


def _outline_window(polygon, shape) -> tuple[int, int, np.ndarray] | None:
    """The outline filled over its own extent, clipped to the page:
    (x0, y0, mask), or None when nothing of it is on the page."""
    h, w = shape
    pts = np.round(np.asarray(polygon, dtype=np.float64)).astype(np.int32)
    if len(pts) < 3:
        return None
    x0, y0 = max(int(pts[:, 0].min()), 0), max(int(pts[:, 1].min()), 0)
    x1, y1 = min(int(pts[:, 0].max()) + 1, w), min(int(pts[:, 1].max()) + 1, h)
    if x1 <= x0 or y1 <= y0:
        return None
    m = np.zeros((y1 - y0, x1 - x0), np.uint8)
    cv2.fillPoly(m, [pts - np.array([x0, y0], np.int32)], 1)
    if not m.any():
        return None
    return x0, y0, m.astype(bool)


def _shared(a, b) -> int:
    """Pixels two outline windows share."""
    (ax, ay, am), (bx, by, bm) = a, b
    x0, y0 = max(ax, bx), max(ay, by)
    x1 = min(ax + am.shape[1], bx + bm.shape[1])
    y1 = min(ay + am.shape[0], by + bm.shape[0])
    if x1 <= x0 or y1 <= y0:
        return 0
    return int((am[y0 - ay:y1 - ay, x0 - ax:x1 - ax]
                & bm[y0 - by:y1 - by, x0 - bx:x1 - bx]).sum())


def segment_seeded(wall_mask: np.ndarray, barrier_mask: np.ndarray,
                   obstacle_mask: np.ndarray, px_per_m: float,
                   outlines: list,
                   door_mask: np.ndarray | None = None,
                   fixture_mask: np.ndarray | None = None,
                   ) -> tuple[np.ndarray, np.ndarray, list[Room]]:
    """segment_rooms, with the AI pointing (docs/adr/0023).

    `outlines` are the seed claims' polygons, (x, y) in px on this canvas.
    Each is shrunk to a seed well inside its room and the room grows from it
    along the free floor, never through a wall, a partition or a sealed
    doorway -- so every edge is a drawn line, and the outline itself is
    thrown away. Floor no seed reaches is no room. Every room returned has
    `existence = "ai"`.

    Unlike segment_rooms, nothing here dilates the walls to close doorways:
    a seed already says which side of an opening is which room, and the
    DOOR_CLOSE_M dilation swallows a small room whole at a large scale.
    """
    shape = wall_mask.shape
    free = ~(wall_mask | barrier_mask | obstacle_mask)
    if fixture_mask is not None:
        free &= ~fixture_mask
    dist = cv2.distanceTransform(free.astype(np.uint8), cv2.DIST_L2, 5)
    doors = door_mask.astype(bool) if door_mask is not None \
        else np.zeros(shape, bool)
    floor = free & ~doors

    # 1. One room seen from two overlapping crops stays one: keep the first.
    windows = []
    for polygon in outlines:
        win = _outline_window(polygon, shape)
        if win is None:
            continue
        if any(_shared(win, o) > SAME_ROOM_OVERLAP * max(win[2].sum(), o[2].sum())
               for o in windows):
            continue
        windows.append(win)
    claimed = np.zeros(shape, np.uint8)
    for x0, y0, m in windows:
        sub = claimed[y0:y0 + m.shape[0], x0:x0 + m.shape[1]]
        sub[m] = np.minimum(sub[m], 1) + 1
    # 2. Floor two outlines claim belongs to neither seed: the walls decide it.
    # 3. Shrink well inside the room, on free floor, off sealed doorways.
    seeds = np.zeros(shape, np.int32)
    shrinks = [int(k * px_per_m) for k in SEED_SHRINK_M] + [SEED_SHRINK_LAST_PX]
    for number, (x0, y0, m) in enumerate(windows, start=1):
        window = np.s_[y0:y0 + m.shape[0], x0:x0 + m.shape[1]]
        own = (m & (claimed[window] == 1)).astype(np.uint8)
        # Padded, so the outline's edge on the page's edge shrinks too.
        own = np.pad(own, 1)
        for k in shrinks:
            seed = cv2.erode(own, _disk(k)).astype(bool)[1:-1, 1:-1] & floor[window]
            if seed.sum() > SEED_MIN_PX:
                break
        else:
            continue
        seeds[window][seed & (seeds[window] == 0)] = number
    # 4. Grow along the free floor, never through a wall or a sealed doorway.
    labels = _grow_along(seeds, floor, int(SEED_REACH_M * px_per_m))
    # 5. A sealed doorway's own floor joins the room beside it.
    labels = _grow_along(labels, free, 3)

    # The same floor under a room as segment_rooms keeps: a seed on the sliver
    # a placard's fill leaves is no room (docs/adr/0012), a dégagement between
    # doors is one.
    def kept(lab, whole) -> bool:
        area_m2 = whole.sum() / px_per_m ** 2
        if area_m2 >= MIN_ROOM_M2:
            return True
        return area_m2 >= MIN_COULOIR_M2 and bool(
            (cv2.dilate(whole.astype(np.uint8), np.ones((3, 3), np.uint8))
             .astype(bool) & doors).any())
    rooms = _rooms(labels, free, obstacle_mask, fixture_mask, px_per_m, kept,
                   existence="ai")
    return free, dist, rooms


def window_masks(rooms: list[Room], pad: int = 0):
    """The rooms' masks over one window that holds them all, `pad` px wider
    and clipped to the page: ((x0, y0), [mask, ...]). For comparing rooms
    without building a page-sized mask for each."""
    h, w = rooms[0].shape
    x0 = max(0, min(r.origin[0] for r in rooms) - pad)
    y0 = max(0, min(r.origin[1] for r in rooms) - pad)
    x1 = min(w, max(r.origin[0] + r.crop.shape[1] for r in rooms) + pad)
    y1 = min(h, max(r.origin[1] + r.crop.shape[0] for r in rooms) + pad)
    out = []
    for r in rooms:
        m = np.zeros((y1 - y0, x1 - x0), bool)
        ox, oy = r.origin[0] - x0, r.origin[1] - y0
        ch, cw = r.crop.shape
        m[oy:oy + ch, ox:ox + cw] = r.crop
        out.append(m)
    return (x0, y0), out


def _apart(a: Room, b: Room) -> bool:
    ax, ay = a.origin
    bx, by = b.origin
    return (ax + a.crop.shape[1] <= bx or bx + b.crop.shape[1] <= ax
            or ay + a.crop.shape[0] <= by or by + b.crop.shape[0] <= ay)


def overlap(a: Room, b: Room) -> int:
    """Pixels the two rooms share."""
    if _apart(a, b):
        return 0
    _, (ma, mb) = window_masks([a, b])
    return int((ma & mb).sum())


def area_px(r: Room) -> int:
    return int(r.crop.sum())


def iou(a: Room, b: Room) -> float:
    shared = overlap(a, b)
    union = area_px(a) + area_px(b) - shared
    return shared / union if union else 1.0


def mask_digest(r: Room) -> str:
    """Identifies a room's floor, pixel for pixel, wherever it lies."""
    import hashlib
    h = hashlib.sha256(np.packbits(r.crop).tobytes())
    h.update(repr((r.origin, r.crop.shape, r.shape)).encode())
    return h.hexdigest()


def _touch(a: Room, b: Room, disk: np.ndarray, margin_px: int) -> bool:
    _, (ma, mb) = window_masks([a, b], pad=margin_px)
    return bool((cv2.dilate(ma.astype(np.uint8), disk).astype(bool) & mb).any())


ADJACENCY_MARGIN_PX = 6   # how close two rooms' masks must sit to call them neighbours


def adjacent_pairs(rooms: list[Room],
                   margin_px: int = ADJACENCY_MARGIN_PX) -> dict[int, list[int]]:
    """Room numbers sharing a boundary, keyed by `Room.number`.

    A wall between two rooms is a gap in both masks, not a shared pixel, so
    "adjacent" is tested by dilating one room's mask and looking for the
    other's -- exactly the reasoning `are_really_one`'s candidate search
    needs to offer only rooms a merge could genuinely fuse (ticket 04).
    """
    disk = _disk(margin_px)
    result: dict[int, list[int]] = {r.number: [] for r in rooms}
    for i, a in enumerate(rooms):
        ax0, ay0, ax1, ay1 = a.bbox
        for b in rooms[i + 1:]:
            bx0, by0, bx1, by1 = b.bbox
            if (ax0 - margin_px > bx1 or bx0 - margin_px > ax1 or
                    ay0 - margin_px > by1 or by0 - margin_px > ay1):
                continue  # bboxes too far apart to touch even dilated
            # Both rooms, on a window over just the two of them -- never the
            # page, which is ~35 MB a mask on an A0 sheet.
            if _touch(a, b, disk, margin_px):
                result[a.number].append(b.number)
                result[b.number].append(a.number)
    return result


# guess_sanitary() was deleted here (plan D3). It typed a room by "small,
# unnamed and full of fixture linework", which is not a fact about the room
# and could not be corrected. roomtype.resolve() replaces it with an
# evidence cascade that records where each verdict came from.
