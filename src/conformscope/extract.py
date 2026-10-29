"""Vector extraction from the floor-plan PDF: calibration, walls, obstacles.

Works on fully-vector plans (PyMuPDF drawings). All heuristics that decide
what counts as an obstacle live here so they can be tuned in one place.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from collections.abc import Collection
from typing import Literal

import cv2
import fitz
import numpy as np
from PIL import Image, ImageDraw

# The destinations a path can be sorted into. A human correction names one of
# these directly. "dashed" keeps the path around for inspection (M4 renders it);
# "ignored" drops it entirely. "structural" is a wall that is *also* thick
# enough to divide apartments, so it lands in both wall lists.
Bucket = Literal["wall", "structural", "wall_line", "obstacle", "door_arc",
                 "placard", "dashed", "ignored"]
BUCKETS: tuple[str, ...] = ("wall", "structural", "wall_line", "obstacle",
                            "door_arc", "placard", "dashed", "ignored")

# --- tunable heuristics -----------------------------------------------------
WALL_FILL_MAX_GREY = 0.85      # fills printing darker than this = wall/structure
STROKE_MAX_GREY = 0.6          # strokes darker than this may be obstacles
DOOR_ARC_MIN_RADIUS_M = 0.55   # open curve paths at least this big = door swing
DASH_SEGMENT_MAX_PT = 3.5      # paths of many tiny segments = dashed decor
WALL_LINE_MIN_M = 1.0          # strokes with a segment this long = partition line
FURNITURE_DENSITY_MAX = 3.5    # items per meter of bbox diagonal; above this,
                                # a stroke is a symbol block (wardrobe, bed),
                                # not a wall line, regardless of its length
FUSED_GAP_M = 0.30             # a CAD export can fuse two symbols into one path
                                # (the single bed and the placard above it on
                                # the sample plan, 1.16 m apart). Strokes closer
                                # than this are one symbol: a dashed croix's own
                                # dashes come apart below ~0.1 m, and 0.25-0.8
                                # splits the sample plan identically
FUSED_BODY_MIN_M = 0.75        # a solid piece this deep on both sides is a body
                                # -- a bed, a bath -- not a stroke that happens
                                # to sit in dashed decor; the same rail as
                                # FIXTURE_SHORT_MAX_M below
ROUNDISH_ASPECT_MIN = 0.85    # bbox width/height this close to 1 -> maybe a circle
ROUNDISH_FILL_MIN = 0.70       # traced-area/bbox-area near a circle's pi/4 (~0.785)
ROUNDISH_FILL_MAX = 0.90       # -- measured 0.78-0.78 on this codebase's own
                                # reference turning circles vs. 0.33/1.0/1.92 on
                                # real fixture symbols of similar aspect ratio
                                # (tests/test_extract.py), so the band is tight
                                # on purpose: it exists only to keep a dashed
                                # reference Ø circle from being mistaken for
                                # equipment, not to recognise circular fixtures.
# A **placard** is drawn as a box with both diagonals struck through. The
# croix is what distinguishes it from a dashed wardrobe outline, and it is
# orientation-free -- a rotated X is still an X -- which is why this rung is
# geometric rather than a search for the letters "PL" (docs/adr/0013).
PLACARD_MIN_SIDE_M = 0.50      # shallower than this is a fixture, not joinery:
                                # nothing hangs in 40cm, and every placard
                                # measured on this plan is >= 0.64 m deep
PLACARD_MAX_SIDE_M = 4.0       # a 5m croix is a barred-off zone, not a placard
PLACARD_DIAG_COVER_MIN = 0.20  # a croix drawn as four corner ticks traces only
                                # a quarter of each diagonal; what keeps a plain
                                # dashed box out is the direction test below,
                                # not this length
PLACARD_DIAG_TOL_PT = 2.0      # the croix is drawn inset from the corners...
PLACARD_DIAG_TOL_FRAC = 0.12   # ...but never by a fifth of the symbol. The
                                # absolute tolerance alone is a 40%-wide band on
                                # a 9.6pt toilet bowl, whose own outline then
                                # reads as a croix (tests/test_placard.py).
PLACARD_DIAG_REACH = 0.20      # the croix still has to run corner to corner,
                                # give or take: architects draw the arms shy of
                                # the corners, and one placard on the sample
                                # plan reaches only 83% of a diagonal. Anything
                                # from 0.18 to 0.30 finds the same twelve and
                                # nothing else, so this is not a knife edge.
PLACARD_DIAG_MAX_DEG = 30.0    # ...and its strokes have to *run along* the
                                # diagonal. A dashed rectangle puts a dash at
                                # each corner, which sits on both diagonals and
                                # reaches both ends of them; only its direction
                                # gives it away, since a box edge is axis-
                                # aligned and a diagonal is not.
# A kitchen appliance -- four, plaque, lave-vaisselle, évier -- and the
# lave-linge and washbasins drawn the same way, are each a small box carrying a
# symbol, and every one buckets as `dashed`: the symbol's short strokes trip
# _is_dashed_decor. The box is found as a **cell** (docs/adr/0014), because the
# same plan also explodes a kitchen block into one path carrying several
# appliances at once, and no per-path rule covers both.
FIXTURE_SEG_MIN_M = 0.25       # a stroke this long can be a cell's side; every
                                # stroke of an "F", a "LV" or a hob is shorter,
                                # so the symbol never walls anything in
FIXTURE_AXIS_TOL_PT = 0.3      # a side runs along an axis; a diagonal is a
                                # croix or a hatch, never a cell's side
FIXTURE_GAP_CLOSE_M = 0.08     # gaps narrower than this are closed before cells
                                # are found: an évier's drainer is lines 5 cm
                                # apart, and must read as one solid, not as a
                                # stack of 5 cm "cells"
FIXTURE_SHORT_MIN_M = 0.35     # the smallest appliance cell on the plan is an
                                # évier's basin, 0.40 m; a jamb, a sill or the
                                # gap between two lines is under 0.20 m
FIXTURE_SHORT_MAX_M = 0.75     # the rail, derived rather than tuned: a cell
                                # this shallow never held a Ø1,50 m circle.
                                # Deeper is a shower tray, a bath or a bed --
                                # floor this rung has no business taking
FIXTURE_LONG_MAX_M = 1.30      # the longest single appliance is the 1.20 m évier
FIXTURE_RECT_MIN = 0.80        # a cell's outer boundary fills its bounding box
                                # at least this well: an appliance is a
                                # rectangle, a corridor's elbow is not
FIXTURE_HOLE_MAX_M2 = 1.0      # a hole enclosed by fixture alone -- the basin
                                # drawn inside an évier -- belongs to it
# A **toilet** is one compact symbol -- bowl and cistern in a single path, the
# bowl polygonised into dozens of short strokes -- with no straight side long
# enough to wall a cell in. Being one path, it is taken by its hull, the way a
# placard is (docs/adr/0015).
TOILET_SHORT_MIN_M = 0.30      # a tap, a handle or a drain is drawn the same
                                # way, and far smaller
TOILET_SHORT_MAX_M = 0.45      # the toilets on the sample plan are 0.36 and
                                # 0.40 m across; the washbasins beside them 0.48
TOILET_LONG_MIN_M = 0.50       # bowl and cistern together are 0.55-0.56 m on
TOILET_LONG_MAX_M = 0.75       # the plan; a long wall-hung pan reaches 0.70
TOILET_ELONGATION_MIN = 1.2    # a toilet projects from its wall -- 1.4 to 1.6
                                # times as long as it is wide here -- where a
                                # chair or a stool of the same size is square
# A dashed line laid down **dash by dash** -- every dash its own solid path,
# nothing to say it belongs to a line -- is still a dashed line (CONTEXT.md
# **Bucket**). PLAN APPARTEMENT draws its red reference circles and clearance
# zones that way: 1.56 pt dashes with 1.44 pt gaps, and a dash-dot of 17-21 pt
# dashes with 4.2 pt gaps. Read one by one, each dash was a solid dark stroke,
# an obstacle. These are paper lengths, not metres: a linetype is drawn on the
# sheet, whatever the scale of the plan under it.
DASH_PIECE_MAX_PT = 36.0       # a dash longer than ~1.3 cm of paper is a line
DASH_JOINED_MAX_PT = 72.0      # ...though two may meet where a closed shape's
                                # pattern starts over, its last dash running
                                # into its first
DASH_PIECE_MAX_ITEMS = 3       # a dash is a stroke or two -- a curve's chords
DASH_GAP_MAX_PT = 8.0          # the gap between two dashes of one line
DASH_TOUCH_PT = 0.5            # closer than this, two pieces are one stroke --
                                # a polyline exported segment by segment, or a
                                # dash broken where it turns a corner
DASH_TURN_MAX_DEG = 30.0       # a gap runs on along both dashes it parts...
DASH_MIN_GAPS = 4              # ...and a dashed line has a few of them,
DASH_GAP_SPREAD = 2.0          # all about the same: within this factor of
DASH_GAP_REGULAR_MIN = 0.8     # their median, for at least this share of them
DASH_CELL_MAX_ENDS = 32        # a dashed line puts ~6 dash ends in a gap-sized
                                # square of paper; PLAN APPARTEMENT packs
                                # thousands into some -- hatching, lettering
                                # -- where no dash can be told from its
                                # neighbours, and pairing them all costs
                                # billions of comparisons. Those are left be.
DIM_TEXT_RE = re.compile(r"^(\d+(?:[.,]\d+))$")
DEFAULT_PT_PER_M = 72 / 2.54   # 1:100 scale on paper: 1 m = 1 cm = 28.35 pt


# Where the scale came from. "measured" is the only one the product's central
# claim covers: the plan's own dimension lines. "assumed" means the fallback
# below invented it, and must reach the auditor rather than stay in the note --
# every measurement in the draft is derived from this number.
CalibrationProvenance = Literal["measured", "assumed", "human"]


@dataclass(frozen=True)
class Calibration:
    pt_per_m: float
    provenance: CalibrationProvenance
    note: str


@dataclass
class PlanExtract:
    page_rect: fitz.Rect
    pt_per_m: float
    calibration_note: str
    calibration_provenance: CalibrationProvenance
    wall_paths: list = field(default_factory=list)      # all filled wall shapes
    structural_paths: list = field(default_factory=list)  # thick walls only (facade/refends)
    wall_line_paths: list = field(default_factory=list) # long stroked partition lines
    obstacle_paths: list = field(default_factory=list)  # solid fixture strokes
    placard_paths: list = field(default_factory=list)   # built-in joinery
    door_arc_paths: list = field(default_factory=list)  # detected door swings
    dashed_paths: list = field(default_factory=list)    # dashed decor (ignored)
    cote_paths: list = field(default_factory=list)      # a cote's line and arrowheads
    text_words: list = field(default_factory=list)
    overridden_indices: set = field(default_factory=set)  # path_index a human bucketed directly


def _grey(color) -> float:
    if color is None:
        return 1.0
    return sum(color) / len(color)


def _printed_fill_grey(path) -> float:
    """How dark a path's fill comes out on the paper: its grey laid over white
    at its fill opacity. Freeda's shower-room floors are a 0.75 grey at half
    opacity -- a pale wash on the sheet, which read at its nominal grey passed
    for poché and filled every shower room solid with wall (CONTEXT.md,
    **Bucket**: a pale fill is a floor finish)."""
    opacity = path.get("fill_opacity")
    opacity = 1.0 if opacity is None else opacity
    return 1.0 - opacity * (1.0 - _grey(path.get("fill")))


def _path_points(path) -> list[tuple[float, float]]:
    pts = []
    for item in path["items"]:
        kind = item[0]
        if kind == "l":
            pts += [tuple(item[1]), tuple(item[2])]
        elif kind == "c":
            pts += [tuple(item[1]), tuple(item[2]), tuple(item[3]), tuple(item[4])]
        elif kind == "re":
            r = item[1]
            pts += [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)]
        elif kind == "qu":
            q = item[1]
            pts += [tuple(q.ul), tuple(q.ur), tuple(q.lr), tuple(q.ll)]
    return pts


def _is_dashed_decor(path) -> bool:
    """CAD exports bake dashes as many tiny disjoint segments in one path.

    Dashed entities (wardrobes, beds, existing turning circles) must not
    count as obstacles. Signature: several items whose median span is tiny.
    """
    spans = []
    for item in path["items"]:
        if item[0] == "l":
            p1, p2 = item[1], item[2]
        elif item[0] == "c":
            p1, p2 = item[1], item[4]
        else:
            continue
        spans.append(math.hypot(p2.x - p1.x, p2.y - p1.y))
    if not spans:
        return False
    if len(spans) == 1 and spans[0] < 1.0:
        return True  # isolated dot
    return len(spans) >= 3 and float(np.median(spans)) < DASH_SEGMENT_MAX_PT


def _polygon_area(pts: list[tuple[float, float]]) -> float:
    """Shoelace area of the points in path order (approximate for a dashed
    outline: gaps between dashes still leave the trace going the same way
    around the shape, so the signed area still comes out close)."""
    n = len(pts)
    if n < 3:
        return 0.0
    total = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2


def is_roundish(path) -> bool:
    """A dashed path shaped like a circle -- a reference Ø turning circle,
    not a fixture (see docs/adr and pipeline._promote_sanitary_obstacles).

    Cheap on purpose: bbox aspect close to 1 AND traced area close to a
    circle's pi/4 share of its bbox. Real fixture symbols with a near-square
    bbox (a toilet's plan-view footprint, a washing machine) measured well
    outside the fill-ratio band on samples/Plan_Logement_Niveau_02.pdf, while
    every dashed Ø1.50 reference circle on that same plan measured almost
    exactly pi/4 -- see tests/test_extract.py.
    """
    r = path["rect"]
    if r.width <= 0 or r.height <= 0:
        return False
    aspect = min(r.width, r.height) / max(r.width, r.height)
    if aspect < ROUNDISH_ASPECT_MIN:
        return False
    fill = _polygon_area(_path_points(path)) / (r.width * r.height)
    return ROUNDISH_FILL_MIN <= fill <= ROUNDISH_FILL_MAX


def _segments(path):
    """The path's straight runs, beziers reduced to their chords."""
    for item in path["items"]:
        if item[0] == "l":
            yield item[1], item[2]
        elif item[0] == "c":
            yield item[1], item[4]


def _diagonal_trace(path, a, b) -> tuple[float, float, float]:
    """How much of the segment a->b this path draws, and how far along it runs.

    Returns (covered fraction, first t reached, last t reached), counting only
    strokes that both *sit on* the diagonal and *run along* it. All three
    matter and none alone is enough: a dashed croix traces barely half its
    diagonal and a ticked one barely a quarter, so length is weak evidence;
    reach is what rejects a lone tick near one corner; and direction is what
    rejects a dashed rectangle, whose four corner dashes otherwise sit on both
    diagonals and reach both ends of them.
    """
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    if length <= 0:
        return 0.0, 1.0, 0.0
    r = path["rect"]
    tol = min(PLACARD_DIAG_TOL_PT, PLACARD_DIAG_TOL_FRAC * min(r.width, r.height))
    cos_min = math.cos(math.radians(PLACARD_DIAG_MAX_DEG))
    covered, lo, hi = 0.0, 1.0, 0.0
    for p1, p2 in _segments(path):
        ts = []
        for q in (p1, p2):
            if abs(dy * (q.x - ax) - dx * (q.y - ay)) / length > tol:
                break
            ts.append(((q.x - ax) * dx + (q.y - ay) * dy) / (length * length))
        if len(ts) < 2:
            continue
        sx, sy = p2.x - p1.x, p2.y - p1.y
        span = math.hypot(sx, sy)
        if span <= 0 or abs(sx * dx + sy * dy) / (span * length) < cos_min:
            continue  # lies on the diagonal, but does not run along it
        covered += span
        lo, hi = min(lo, *ts), max(hi, *ts)
    return covered / length, lo, hi


def is_placard(path, pt_per_m: float) -> bool:
    """A placard-scale box with both diagonals struck through (docs/adr/0012).

    Shape alone, with no reference to the letters "PL": on both sample plans
    that lettering is linework rather than text, so `page.get_text("words")`
    never sees it. Being geometric also makes the rung orientation-free, which
    is what a plan drawn sideways needs.
    """
    # CONTEXT.md defines the symbol as two crossing *dashed* diagonals, and
    # every placard on the sample plan is drawn that way. Holding to it also
    # keeps this rung clear of the wall classifier, which classify_path
    # consults first and which a solid metre-long box satisfies.
    if not _is_dashed_decor(path):
        return False
    r = path["rect"]
    if min(r.width, r.height) < PLACARD_MIN_SIDE_M * pt_per_m:
        return False
    if max(r.width, r.height) > PLACARD_MAX_SIDE_M * pt_per_m:
        return False
    for a, b in (((r.x0, r.y0), (r.x1, r.y1)), ((r.x0, r.y1), (r.x1, r.y0))):
        cover, lo, hi = _diagonal_trace(path, a, b)
        if cover < PLACARD_DIAG_COVER_MIN:
            return False
        if lo > PLACARD_DIAG_REACH or hi < 1 - PLACARD_DIAG_REACH:
            return False
    return True


def _is_door_arc(path, pt_per_m: float) -> bool:
    """Open, curve-dominated path with a door-sized bbox -> swing arc."""
    items = path["items"]
    curves = sum(1 for it in items if it[0] == "c")
    if curves == 0 or curves < len(items) / 2:
        return False
    r = path["rect"]
    size = max(r.width, r.height) / pt_per_m
    if size < DOOR_ARC_MIN_RADIUS_M:
        return False
    pts = _path_points(path)
    if len(pts) < 2:
        return False
    start, end = pts[0], pts[-1]
    gap = math.hypot(start[0] - end[0], start[1] - end[1])
    return gap > 0.25 * max(r.width, r.height)  # open arc, not a closed bowl


def segment_density(path, pt_per_m: float) -> float:
    """Path items per meter of bbox diagonal.

    Furniture/symbol blocks (wardrobes, beds) pack many short segments
    into a small footprint; wall lines are comparatively sparse relative
    to their length, even with a jog or step. This is the signal that
    separates a wardrobe from a real wall when both have a bbox edge
    longer than WALL_LINE_MIN_M (see tests/test_extract.py).
    """
    r = path["rect"]
    diag_m = math.hypot(r.width, r.height) / pt_per_m
    return len(path["items"]) / max(diag_m, 0.01)


def is_wall_line(path, pt_per_m: float) -> bool:
    """A stroked path is a partition/wall line, not a furniture symbol."""
    if segment_density(path, pt_per_m) > FURNITURE_DENSITY_MAX:
        return False
    longest = 0.0
    for item in path["items"]:
        if item[0] == "l":
            p1, p2 = item[1], item[2]
            longest = max(longest, math.hypot(p2.x - p1.x, p2.y - p1.y))
        elif item[0] == "re":
            r = item[1]
            longest = max(longest, r.width, r.height)
    return longest >= WALL_LINE_MIN_M * pt_per_m


CM_TEXT_RE = re.compile(r"^[1-9]\d{2,3}$")  # « 472 »: a bare centimetre cote
CM_COTE_MIN, CM_COTE_MAX = 100, 2000  # 1 m to 20 m; « 2024 » is a year, « 0098 » a code
TICK_MAX_PT = 8.0              # a tick or extension stub is a speck beside its line
TICK_MIN_PT = 1.0              # ...but a stroke, not a dot
TICK_MIN_DEG = 30.0            # it crosses the line; a collinear overshoot does not
COTE_AXIS_TOL_PT = 0.5         # strokes this close to the line's axis lie on it
COTE_RUN_JOIN_PT = 1.0         # collinear strokes this close draw one continuous line
COTE_TEXT_INTO_PT = 1.5        # a figure's descenders may dip onto its line
COTE_CLUSTER_TOL = 0.05        # cotes agreeing within 5% state the same scale
COTE_STYLE_TOL = 0.02          # per colour channel: "drawn in the same stroke"


def _stroke_rgb(path) -> tuple[float, float, float]:
    color = path.get("color") or (-1.0, -1.0, -1.0)
    if len(color) == 1:
        return (color[0],) * 3
    if len(color) == 4:            # CMYK, compared as given -- only equality matters
        return tuple(color[:3])
    return tuple(color)


def _cote_value_m(text: str) -> float | None:
    """The length a word states, in metres, if it can be a cote at all:
    « 4,72 » (metres, 1-60) or « 472 » (bare centimetres, 100-2000)."""
    m = DIM_TEXT_RE.match(text)
    if m:
        val = float(m.group(1).replace(",", "."))
        return val if 1.0 <= val <= 60.0 else None
    if CM_TEXT_RE.match(text) and CM_COTE_MIN <= int(text) <= CM_COTE_MAX:
        return int(text) / 100
    return None


def _ticked_cotes(words, drawings) -> list[tuple[float, set[int]]]:
    """(pt per metre, path_index of its line and ticks) for every figure set
    beside a continuous dimension line closed by end ticks.

    The PLAN APPARTEMENT / Freeda form, where the gap reader (_gap_ratios)
    finds nothing: a hairline runs unbroken from tick to tick (overshooting
    each by a few points, and often chained -- one line, several figures,
    a tick at every link), each tick an oblique slash or a short stroke
    crossing it, and the figure sits just above it or, read sideways, just
    beside it. The span is between the nearest ticks either side of the
    figure, so a chain gives each link its own length. Nothing here decides
    whether a figure is a cote: a logement number beside a framed cell, a
    furniture reference in its box, can come out with a span too -- it is
    read_cotes()'s cluster that throws away the ones that disagree with the
    sheet. Line, overshoots and ticks must share one stroke colour -- not a
    colour rule, a consistency one: a door leaf crossing the line is not
    taken for a tick. Axis-aligned only, as the gap reader is: a site-plan inset's
    skewed cotes never reach here.
    """
    figures = []
    for w in words:
        val = _cote_value_m(w[4])
        if val is not None:
            figures.append((val, w[:4]))
    if not figures:
        return []
    # Every straight stroke, as rows of x0, y0, x1, y1, path_index, r, g, b.
    rows = [(it[1].x, it[1].y, it[2].x, it[2].y, i, *_stroke_rgb(path))
            for i, path in enumerate(drawings) if path.get("fill") is None
            for it in path["items"] if it[0] == "l"]
    if not rows:
        return []
    seg = np.array(rows, dtype=float)
    length = np.hypot(seg[:, 2] - seg[:, 0], seg[:, 3] - seg[:, 1])
    sin_min = math.sin(math.radians(TICK_MIN_DEG))
    frames = {}
    for horizontal in (True, False):
        # Work in the figure's own frame: u runs along its reading direction,
        # v across it. A sideways figure's line is vertical, so swap axes.
        u0, v0, u1, v1 = ((seg[:, 0], seg[:, 1], seg[:, 2], seg[:, 3]) if horizontal
                          else (seg[:, 1], seg[:, 0], seg[:, 3], seg[:, 2]))
        along = np.nonzero(np.abs(v1 - v0) < COTE_AXIS_TOL_PT)[0]
        along = along[np.argsort((v0[along] + v1[along]) / 2)]
        # Ticks: short strokes steep enough across the line not to be its
        # own overshoot.
        tick = np.nonzero((length > TICK_MIN_PT) & (length <= TICK_MAX_PT)
                          & (np.abs(v1 - v0) >= sin_min * length))[0]
        frames[horizontal] = (u0, v0, u1, v1, along,
                              (v0[along] + v1[along]) / 2, tick)
    found = []
    for val, (x0, y0, x1, y1) in figures:
        horizontal = (x1 - x0) >= (y1 - y0)
        u0, v0, u1, v1, along, v_along, tick = frames[horizontal]
        fu0, fu1, fv0, fv1 = (x0, x1, y0, y1) if horizontal else (y0, y1, x0, x1)
        fu = (fu0 + fu1) / 2
        # Candidate lines: along the figure, passing under its middle, and
        # within reach of its box -- beside it, or dipped into by descenders.
        lo, hi = np.searchsorted(v_along, [fv0 - COTE_TEXT_NEAR_PT,
                                           fv1 + COTE_TEXT_NEAR_PT])
        near = along[lo:hi]
        v = v_along[lo:hi]
        gap = np.where(v < fv0, fv0 - v, np.where(v > fv1, v - fv1, 0.0))
        dip = np.minimum(v - fv0, fv1 - v)
        ok = np.where(gap > 0, gap <= COTE_TEXT_NEAR_PT, dip <= COTE_TEXT_INTO_PT) \
            & (np.minimum(u0[near], u1[near]) < fu) & (np.maximum(u0[near], u1[near]) > fu)
        for j in np.nonzero(ok)[0][np.argsort(gap[ok], kind="stable")]:
            k, axis = near[j], v[j]
            # A dimension line, its overshoots and its ticks are one drawing in
            # one stroke style; a door leaf or a jamb crossing it is not part of
            # it, and taken for a tick it would cut the link short.
            style = seg[k, 5:8]
            a_lo, a_hi = np.searchsorted(v_along, [axis - COTE_AXIS_TOL_PT,
                                                   axis + COTE_AXIS_TOL_PT])
            on_axis = along[a_lo:a_hi]
            on_axis = on_axis[np.all(np.abs(seg[on_axis, 5:8] - style)
                                     < COTE_STYLE_TOL, axis=1)]
            s_lo = np.minimum(u0[on_axis], u1[on_axis])
            s_hi = np.maximum(u0[on_axis], u1[on_axis])
            # The continuous run the figure sits on: collinear strokes chained
            # end to end, whichever paths drew them.
            run_lo, run_hi = min(u0[k], u1[k]), max(u0[k], u1[k])
            while True:
                joined = (s_lo <= run_hi + COTE_RUN_JOIN_PT) & (s_hi >= run_lo - COTE_RUN_JOIN_PT)
                new_lo, new_hi = s_lo[joined].min(), s_hi[joined].max()
                if new_lo >= run_lo and new_hi <= run_hi:
                    break
                run_lo, run_hi = new_lo, new_hi
            run = on_axis[joined]
            # Ticks in the line's own style crossing (or ending on) its axis
            # inside the run.
            tk = tick[(np.minimum(v0[tick], v1[tick]) <= axis + COTE_AXIS_TOL_PT)
                      & (np.maximum(v0[tick], v1[tick]) >= axis - COTE_AXIS_TOL_PT)]
            tk = tk[np.all(np.abs(seg[tk, 5:8] - style) < COTE_STYLE_TOL, axis=1)]
            t = np.clip((axis - v0[tk]) / (v1[tk] - v0[tk]), 0, 1)
            at = u0[tk] + t * (u1[tk] - u0[tk])
            inside = (at >= run_lo - COTE_AXIS_TOL_PT) & (at <= run_hi + COTE_AXIS_TOL_PT)
            tk, at = tk[inside], at[inside]
            before, after = at[at < fu], at[at > fu]
            if not len(before) or not len(after):
                continue
            a, b = before.max(), after.min()
            # The figure stands inside its own link, not straddling a tick.
            if fu0 < a - COTE_AXIS_TOL_PT or fu1 > b + COTE_AXIS_TOL_PT:
                continue
            ends = tk[(np.abs(at - a) < COTE_AXIS_TOL_PT) | (np.abs(at - b) < COTE_AXIS_TOL_PT)]
            paths = {int(seg[i, 4]) for i in run} | {int(seg[i, 4]) for i in ends}
            # Only a path drawn wholly as cote linework leaves the buckets: a
            # wall outline whose one edge happens to run along the cote keeps
            # its walls.
            found.append(((b - a) / val,
                          {i for i in paths if _cote_shaped(drawings[i], horizontal)}))
            break
    return found


def _cote_shaped(path, horizontal: bool) -> bool:
    """Every stroke of the path is a straight piece of dimension linework:
    along the line, or a tick/extension stub no longer than TICK_MAX_PT."""
    for it in path["items"]:
        if it[0] != "l":
            return False
        p, q = it[1], it[2]
        across = abs(q.y - p.y) if horizontal else abs(q.x - p.x)
        if across >= COTE_AXIS_TOL_PT and math.hypot(q.x - p.x, q.y - p.y) > TICK_MAX_PT:
            return False
    return True


def read_cotes(page: fitz.Page, drawings=None, words=None
               ) -> tuple[Calibration, set[int]]:
    """The page's calibration, and the path_index of every dimension line
    that stated it in the bare-centimetre ticked form (see _ticked_cotes).

    Those lines are cotes -- claims, never evidence (CONTEXT.md, ADR-0016)
    -- and must leave the wall/partition buckets: drawn wall face to wall
    face, a grey hairline is otherwise filed as a partition and cuts the
    séjour along its own cote. Only lines whose figure joined the cluster
    count; a stray figure's line stays whatever it was.
    """
    words = page.get_text("words") if words is None else words
    drawings = page.get_drawings() if drawings is None else drawings
    gap = _gap_ratios(words, drawings)
    ticked = _ticked_cotes(words, drawings)
    ratios = gap + [r for r, _ in ticked]
    if ratios:
        med = float(np.median(ratios))
        agrees = lambda r: abs(r / med - 1) < COTE_CLUSTER_TOL
        cluster = [r for r in sorted(ratios) if agrees(r)]
        if len(cluster) >= 2:
            measured = float(np.mean(cluster))
            paths = {i for r, p in ticked if agrees(r)
                     for i in p}
            return (Calibration(measured, "measured",
                                f"measured {measured:.2f} pt/m from "
                                f"{len(cluster)} dimension lines"), paths)
    return (Calibration(DEFAULT_PT_PER_M, "assumed",
                        "assumed 1:100 (no dimension lines matched)"), set())


def calibrate(page: fitz.Page) -> Calibration:
    """Measure pt/m from the plan's own **cotes** (see read_cotes)."""
    return read_cotes(page)[0]


def _gap_ratios(words, drawings) -> list[float]:
    """pt per metre for every figure sitting in a dimension line's gap.

    CAD dimension lines are drawn as two collinear segments with a gap where
    the value text sits. For each numeric word, find such a flanking pair and
    divide the outer span by the stated value; the true scale is where those
    ratios cluster. (Exported PDFs are often rescaled, so the nominal 1:100
    cannot be trusted.)
    """
    dims = []
    for w in words:
        val = _cote_value_m(w[4])   # « 4,72 » or « 472 », in metres either way
        if val is not None:
            dims.append((val, fitz.Rect(w[:4])))
    h_segs, v_segs = [], []
    for path in drawings:
        for item in path["items"]:
            if item[0] != "l":
                continue
            p1, p2 = item[1], item[2]
            if math.hypot(p2.x - p1.x, p2.y - p1.y) < 15:
                continue
            if abs(p2.y - p1.y) < 0.5:
                h_segs.append((min(p1.x, p2.x), max(p1.x, p2.x), p1.y))
            elif abs(p2.x - p1.x) < 0.5:
                v_segs.append((min(p1.y, p2.y), max(p1.y, p2.y), p1.x))

    def flanking_span(cx, cy, segs, get_axis_center):
        """Outer span of two collinear segments whose gap contains (cx along axis)."""
        left = [s for s in segs if abs(get_axis_center(s) - cy) < 6 and s[1] <= cx + 12]
        right = [s for s in segs if abs(get_axis_center(s) - cy) < 6 and s[0] >= cx - 12]
        if not left or not right:
            return None
        l = max(left, key=lambda s: s[1])
        r = min(right, key=lambda s: s[0])
        if r[0] - l[1] > 25:  # gap too wide to be a dimension text gap
            return None
        return r[1] - l[0]

    ratios = []
    for val, rect in dims:
        cx, cy = (rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2
        span = flanking_span(cx, cy, h_segs, lambda s: s[2])
        if span is None:
            span = flanking_span(cy, cx, v_segs, lambda s: s[2])
        if span:
            ratios.append(span / val)
    return ratios


def classify_path(path, pt_per_m: float) -> Bucket:
    """Which bucket a path falls into, on the evidence alone.

    Pure and side-effect free so a human correction can bypass it wholesale
    (see extract_plan's `overrides`) and so M4's suspect queue can ask "what
    would the classifier say?" without re-running extraction.
    """
    fill_grey = _printed_fill_grey(path)
    stroke_grey = _grey(path.get("color"))
    if path.get("fill") is not None and fill_grey < WALL_FILL_MAX_GREY:
        # thick structural walls (facade, refends) are also plain walls
        return "structural" if fill_grey < 0.6 else "wall"
    if path.get("color") is None:
        return "ignored"  # fill-only light tint (floor shading)
    # Door arcs are checked before the dashed/light-stroke filters below:
    # CAD exports often draw door swings in a light grey (fails
    # STROKE_MAX_GREY) that would otherwise be discarded as decorative
    # before this shape-based check ever ran.
    if _is_door_arc(path, pt_per_m):
        return "door_arc"
    solid = path.get("dashes") in (None, "", "[] 0")
    dark = stroke_grey <= STROKE_MAX_GREY
    # A solid dark stroke shaped like a wall IS a wall, even when its median
    # segment is short. Wall outlines carry many tiny thickness/jamb jogs
    # (e.g. spans of 1.4-3.7pt around two 36pt and 41pt runs either side of a
    # door opening) that drag the median down into _is_dashed_decor's range.
    # is_wall_line's density check is what keeps furniture blocks out here.
    if solid and dark and is_wall_line(path, pt_per_m):
        return "wall_line"
    # Checked ahead of the dashed fallthrough it would otherwise land in: a
    # placard is drawn in exactly the dashed linework this codebase protects
    # as decor, and it is the one dashed symbol that is never decor.
    if is_placard(path, pt_per_m):
        return "placard"
    if not solid or _is_dashed_decor(path):
        return "dashed"
    if not dark:
        return "ignored"  # light decorative stroke
    return "obstacle"


def _item_box(item) -> tuple[float, float, float, float]:
    """An item's extent, degenerate for a straight axis-aligned line -- which
    is why this is not fitz.Rect: an empty Rect drops out of `|` and
    `intersects`, and every side of a bed is such a line."""
    kind = item[0]
    if kind == "re":
        pts = [item[1].tl, item[1].br]
    elif kind == "qu":
        pts = [item[1].ul, item[1].ur, item[1].ll, item[1].lr]
    else:
        pts = item[1:]
    xs, ys = [p.x for p in pts], [p.y for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _fused_pieces(path, pt_per_m: float) -> list:
    """The path cut into groups of items no closer than FUSED_GAP_M to another
    group, each a path of its own with the parent's style and path_index."""
    boxes = [_item_box(it) for it in path["items"]]
    gap = FUSED_GAP_M * pt_per_m
    parent = list(range(len(boxes)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(boxes):
        for j in range(i + 1, len(boxes)):
            b = boxes[j]
            if (a[0] - gap <= b[2] and b[0] - gap <= a[2]
                    and a[1] - gap <= b[3] and b[1] - gap <= a[3]):
                parent[root(i)] = root(j)
    groups: dict[int, list[int]] = {}
    for i in range(len(boxes)):
        groups.setdefault(root(i), []).append(i)
    return [_sub_path(path, idx, boxes) for idx in groups.values()]


def _sub_path(path, idx: list[int], boxes) -> dict:
    return {**path, "items": [path["items"][i] for i in idx],
            "rect": fitz.Rect(min(boxes[i][0] for i in idx),
                              min(boxes[i][1] for i in idx),
                              max(boxes[i][2] for i in idx),
                              max(boxes[i][3] for i in idx))}


def unfuse(path, pt_per_m: float) -> list[tuple[dict, Bucket]]:
    """A path headed for `dashed`, re-read as the symbols it may be fused from.

    A piece leaves decor only as a placard, or as an obstacle with a body's
    footprint (FUSED_BODY_MIN_M both ways). Everything else -- dashes, stray
    strokes, a flat sill -- stays together as the one decor path it was, so a
    path with no such piece comes back exactly as it went in.
    """
    kept, decor = [], []
    for piece in _fused_pieces(path, pt_per_m):
        bucket = classify_path(piece, pt_per_m)
        r = piece["rect"]
        body = min(r.width, r.height) >= FUSED_BODY_MIN_M * pt_per_m
        if bucket == "placard" or (bucket == "obstacle" and body):
            kept.append((piece, bucket))
        else:
            decor.append(piece)
    if not kept:
        return [(path, "dashed")]
    if decor:
        items = [it for p in decor for it in p["items"]]
        boxes = [_item_box(it) for it in items]
        kept.append((_sub_path({**path, "items": items}, list(range(len(items))),
                               boxes), "dashed"))
    return kept


def _declared_solid(path) -> bool:
    return path.get("dashes") in (None, "", "[] 0")


def is_dashed_closed_shape(path) -> bool:
    """A dashed outline that closes on itself -- an architect's reference
    circle, a clearance zone -- which is never a **fixture** (CONTEXT.md
    **Bucket**), however it was drawn: declared dashed, or a run of dashes
    `dash_runs` closed into a loop."""
    if path.get("dash_closed"):
        return True
    if _declared_solid(path):
        return False
    if path.get("closePath") or any(it[0] in ("re", "qu") for it in path["items"]):
        return True
    pts = _path_points(path)
    return len(pts) >= 3 and math.hypot(pts[0][0] - pts[-1][0],
                                        pts[0][1] - pts[-1][1]) <= DASH_TOUCH_PT


def _unit(dx: float, dy: float):
    n = math.hypot(dx, dy)
    return (dx / n, dy / n) if n > 1e-6 else None


def _dash_piece(path):
    """A path that may be one dash of a line drawn dash by dash: its length,
    and each end as (point, outward direction) -- None for a dot's direction.
    None when the path cannot be a dash at all."""
    items = path["items"]
    if (path.get("fill") is not None or path.get("color") is None
            or not _declared_solid(path)
            or not 1 <= len(items) <= DASH_PIECE_MAX_ITEMS
            or any(it[0] not in ("l", "c") for it in items)):
        return None
    length = sum(math.hypot(it[-1].x - it[1].x, it[-1].y - it[1].y)
                 for it in items)
    if length > DASH_PIECE_MAX_PT:
        return None
    first, last = items[0], items[-1]
    a, b = first[1], last[-1]
    # Outward: away from the stroke, along its tangent at that end. A
    # curve's tangent is towards its control point, or its far end if the
    # control point sits on the end.
    toward_a = first[2] if math.hypot(first[2].x - a.x, first[2].y - a.y) > 1e-6 \
        else first[-1]
    toward_b = last[-2] if math.hypot(last[-2].x - b.x, last[-2].y - b.y) > 1e-6 \
        else last[1]
    return length, ((a.x, a.y), _unit(a.x - toward_a.x, a.y - toward_a.y)), \
        ((b.x, b.y), _unit(b.x - toward_b.x, b.y - toward_b.y))


_DASH_TURN_COS = math.cos(math.radians(DASH_TURN_MAX_DEG))


def _dash_gap(end_a, end_b) -> float | None:
    """The gap between two dash ends if one line runs on through it, or None.

    It runs on when the gap continues both dashes -- straight on, or around
    a bend as a circle's dashes do -- or when it turns a corner: both dashes,
    run on, meet within a gap's length. Two ends that touch are one stroke.
    """
    (a, u), (b, v) = end_a, end_b
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy)
    if d <= DASH_TOUCH_PT:
        return d
    if d > DASH_GAP_MAX_PT:
        return None
    g = (dx / d, dy / d)
    if ((u is None or u[0] * g[0] + u[1] * g[1] >= _DASH_TURN_COS)
            and (v is None or -(v[0] * g[0] + v[1] * g[1]) >= _DASH_TURN_COS)):
        return d
    if u is None or v is None:
        return None
    cross = u[0] * v[1] - u[1] * v[0]
    if abs(cross) < 1e-6:
        return None  # parallel: side by side, as a hatch's strokes are
    s = (dx * v[1] - dy * v[0]) / cross
    t = (dx * u[1] - dy * u[0]) / cross
    if s < -DASH_TOUCH_PT or t < -DASH_TOUCH_PT or s + t > DASH_GAP_MAX_PT:
        return None
    return max(s + t, d)


def _style(path) -> tuple:
    return (tuple(round(c, 3) for c in path["color"]),
            round(path.get("width") or 0.0, 2))


def dash_runs(drawings, skip: Collection[int] = ()) -> list[tuple[list, bool]]:
    """Every line drawn dash by dash, as (pieces, closed).

    `pieces` is the run in drawing order along the line: (path_index,
    reversed) for each dash, `reversed` when the dash was drawn against the
    run. A run is short strokes sharing one stroke style, each running on
    into the next across a gap -- straight on, along a curve, or round a
    corner -- with at least DASH_MIN_GAPS gaps, nearly all of one length.
    Colour enters only as "the same style as the next dash": it never says
    whether a line is dashed, and a solid red wall stays a wall.

    A long solid stroke parts a run: a wall whose end happens to meet a
    dashed line is not one of its dashes. `skip` are paths already spoken
    for -- a human's bucket, a cote.
    """
    pieces = {}
    for i, path in enumerate(drawings):
        if i not in skip and (piece := _dash_piece(path)) is not None:
            pieces[i] = piece
    # Ends of one style that a line could run on through are joined closest
    # first, each end at most once and two pieces at most once, so a run is a
    # chain: every piece has at most one neighbour at either end.
    cell = DASH_GAP_MAX_PT
    grid: dict[tuple, list] = {}
    for i, piece in pieces.items():
        for e in (0, 1):
            (x, y), _ = piece[1 + e]
            grid.setdefault((_style(drawings[i]), int(x // cell), int(y // cell)),
                            []).append((i, e))
    grid = {k: ends for k, ends in grid.items() if len(ends) <= DASH_CELL_MAX_ENDS}
    pairs = []
    for (style, gx, gy), ends in grid.items():
        for i, e in ends:
            mine = pieces[i][1 + e]
            for nx in (gx - 1, gx, gx + 1):
                for ny in (gy - 1, gy, gy + 1):
                    for j, f in grid.get((style, nx, ny), ()):
                        if j <= i:
                            continue
                        gap = _dash_gap(mine, pieces[j][1 + f])
                        if gap is not None:
                            pairs.append((gap, i, e, j, f))
    link: dict[tuple, tuple] = {}
    joined = set()
    for gap, i, e, j, f in sorted(pairs):
        if (i, e) in link or (j, f) in link or (i, j) in joined:
            continue
        link[(i, e)], link[(j, f)] = (j, f, gap), (i, e, gap)
        joined.add((i, j))

    runs, seen = [], set()
    for start in pieces:
        if start in seen:
            continue
        # Walk back to the head of the chain -- or all the way round, back
        # to `start`, when the run closes on itself -- then forward along it.
        i, e, closed = start, 0, False
        while (i, e) in link:
            j, f, _ = link[(i, e)]
            i, e = j, 1 - f
            if i == start:
                closed = True
                break
        head, enter = (start, 0) if closed else (i, e)
        chain, gaps = [], []
        i = head
        while True:
            seen.add(i)
            chain.append((i, enter == 1))
            out = (i, 1 - enter)
            if out not in link:
                break
            i, enter, gap = link[out]
            gaps.append(gap)
            if i == head:
                break  # that gap closed the loop
        runs += _dashed_stretches(chain, gaps, closed, pieces)
    return runs


def _dashed_stretches(chain, gaps, closed: bool, pieces) -> list[tuple[list, bool]]:
    """The parts of one chain that are dashed lines.

    `gaps[k]` follows `chain[k]`; a closed chain has one more, back to its
    start. Pieces that touch are one dash. The chain is cut at every dash too
    long to be one, and each part is kept if its gaps are many and regular.
    """
    if closed:
        # Start right after a real gap, so no dash straddles the seam.
        real = [k for k, g in enumerate(gaps) if g > DASH_TOUCH_PT]
        if not real:
            return []  # a solid closed outline
        k = real[0] + 1
        chain, gaps = chain[k:] + chain[:k], gaps[k:] + gaps[:k]
    dashes, after = [[chain[0]]], []   # after[k]: the gap following dashes[k]
    for piece, gap in zip(chain[1:], gaps):
        if gap <= DASH_TOUCH_PT:
            dashes[-1].append(piece)
        else:
            after.append(gap)
            dashes.append([piece])
    if closed:
        after.append(gaps[-1])
    long_ = [k for k, d in enumerate(dashes)
             if sum(pieces[i][0] for i, _ in d) > DASH_JOINED_MAX_PT]
    whole = closed and not long_
    if closed and long_:
        # Open the loop at a long stroke: what is left is a line with ends.
        k = long_[0] + 1
        dashes, after = dashes[k:] + dashes[:k], after[k:] + after[:k]
        long_ = [(j - k) % len(dashes) for j in long_]
    stretches, cur = [], []
    for k in range(len(dashes)):
        if k in long_:
            stretches.append(cur)
            cur = []
        else:
            cur.append(k)
    stretches.append(cur)

    runs = []
    for ks in stretches:
        if not ks:
            continue
        gs = after[ks[0]:ks[-1] + (1 if whole else 0)]
        if len(gs) < DASH_MIN_GAPS:
            continue
        med = float(np.median(gs))
        regular = sum(med / DASH_GAP_SPREAD <= g <= med * DASH_GAP_SPREAD
                      for g in gs)
        if regular >= DASH_GAP_REGULAR_MIN * len(gs):
            runs.append(([p for k in ks for p in dashes[k]], whole))
    return runs


def _reversed_item(item):
    return (item[0], *item[:0:-1])


def dashed_line_path(drawings, pieces, closed: bool) -> dict:
    """One run of dashes as the one dashed path it is drawn as.

    It keeps the path_index of its first dash in drawing order, so a stored
    correction (D1) never moves; `dash_pieces` names every dash it took in.
    Its items run along the line, which is what lets is_roundish read a
    circle drawn dash by dash as the circle it is.
    """
    items = []
    for i, rev in pieces:
        its = drawings[i]["items"]
        items += [_reversed_item(it) for it in reversed(its)] if rev else its
    first = min(i for i, _ in pieces)
    path = {**drawings[first], "items": items, "path_index": first,
            "dash_pieces": sorted(i for i, _ in pieces), "dash_closed": closed}
    boxes = [_item_box(it) for it in items]
    return _sub_path(path, list(range(len(items))), boxes)


COTE_LINE_THICK_MAX_PT = 1.0   # a cote's line is a hairline; a wall has depth
COTE_LINE_MIN_PT = 8.0         # shorter than this is an arrowhead or a tick
COTE_TEXT_NEAR_PT = 6.0        # its figure is written right alongside it
COTE_HEAD_MAX_PT = 1.5         # an arrowhead is a speck at the line's end


def cote_indices(drawings, words) -> set[int]:
    """path_index of every **cote**'s line and arrowheads.

    A cote is a claim, never evidence (CONTEXT.md, docs/adr/0016): it must not
    reach a wall, obstacle or partition mask. Left to classify_path, its line
    was filed as an obstacle -- carved out of the floor like a solid thing --
    and its arrowheads as structural wall, which on the sample plan broke the
    1,39 m communs couloir in two exactly where the cote measures it.
    """
    figures = [fitz.Rect(w[:4]) for w in words if DIM_TEXT_RE.match(w[4])]
    lines = {}
    for i, path in enumerate(drawings):
        r = path["rect"]
        if (path.get("fill") is None
                and all(it[0] == "l" for it in path["items"])
                and min(r.width, r.height) <= COTE_LINE_THICK_MAX_PT
                and max(r.width, r.height) >= COTE_LINE_MIN_PT):
            near = fitz.Rect(r.x0 - COTE_TEXT_NEAR_PT, r.y0 - COTE_TEXT_NEAR_PT,
                             r.x1 + COTE_TEXT_NEAR_PT, r.y1 + COTE_TEXT_NEAR_PT)
            if any(near.intersects(f) for f in figures):
                lines[i] = path
    ends = [p for path in lines.values() for it in path["items"] for p in it[1:3]]
    heads = set()
    for i, path in enumerate(drawings):
        r = path["rect"]
        if i in lines or max(r.width, r.height) > COTE_HEAD_MAX_PT:
            continue
        cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
        if any(abs(cx - e.x) < 1.0 and abs(cy - e.y) < 1.0 for e in ends):
            heads.add(i)
    return set(lines) | heads


def _file_in_bucket(ex: PlanExtract, path, bucket: Bucket) -> None:
    if bucket not in BUCKETS:
        raise ValueError(f"unknown bucket {bucket!r}; expected one of {BUCKETS}")
    if bucket in ("wall", "structural"):
        ex.wall_paths.append(path)
        if bucket == "structural":
            ex.structural_paths.append(path)
    elif bucket == "wall_line":
        ex.wall_line_paths.append(path)
    elif bucket == "obstacle":
        ex.obstacle_paths.append(path)
    elif bucket == "door_arc":
        ex.door_arc_paths.append(path)
    elif bucket == "placard":
        ex.placard_paths.append(path)
    elif bucket == "dashed":
        ex.dashed_paths.append(path)
    # "ignored" is dropped on purpose: it contributes to no mask


def extract_plan(doc: fitz.Document, page_index: int = 0,
                 pt_per_m_override: float | None = None,
                 overrides: dict[int, Bucket] | None = None) -> PlanExtract:
    """Sort the page's vector paths into buckets.

    `overrides` maps path_index -> bucket and is consulted **before**
    classify_path, so a human verdict ("path 147 IS a wall") wins outright
    rather than being re-litigated by the heuristics it is there to correct.
    """
    page = doc[page_index]
    # A /Rotate page renders upright but get_drawings() answers in the
    # unrotated frame, so every mask would land a quarter-turn off the
    # drawing. Baking the rotation into the content keeps the page looking
    # the same and puts paths, words and the render in one frame.
    if page.rotation:
        page.remove_rotation()
    words = page.get_text("words")
    # get_drawings() order is deterministic for a given PDF, which is what
    # makes path_index a durable key for stored corrections (D1).
    drawings = page.get_drawings()
    # Read even under a forced scale: the cotes found are claims to keep off
    # the wall masks whoever set the scale.
    cal, ticked_cotes = read_cotes(page, drawings, words)
    if pt_per_m_override:
        cal = Calibration(pt_per_m_override, "human",
                          f"échelle forcée ({pt_per_m_override:g} pt/m)")
    pt_per_m = cal.pt_per_m
    ex = PlanExtract(page_rect=page.rect, pt_per_m=pt_per_m,
                     calibration_note=cal.note,
                     calibration_provenance=cal.provenance,
                     text_words=words)
    overrides = overrides or {}
    cotes = cote_indices(drawings, ex.text_words) | ticked_cotes
    # A line drawn dash by dash is filed whole, under its first dash's index;
    # its other dashes are taken in with it. A human's bucket on that index
    # is a ruling on the whole line. One on any other dash -- stored before
    # its line was read as one -- keeps that dash theirs, out of the line.
    dashes, runs = set(), {}
    for pieces, closed in dash_runs(drawings, skip=cotes):
        first = min(i for i, _ in pieces)
        if first not in overrides:
            kept = [p for p in pieces if p[0] not in overrides]
            closed = closed and len(kept) == len(pieces)
            pieces = kept
        runs[first] = dashed_line_path(drawings, pieces, closed)
        dashes.update(i for i, _ in pieces)
    for path_index, path in enumerate(drawings):
        path["path_index"] = path_index
        if path_index in dashes:
            if path_index in runs:
                bucket = overrides.get(path_index, "dashed")
                if path_index in overrides:
                    ex.overridden_indices.add(path_index)
                _file_in_bucket(ex, runs[path_index], bucket)
            continue
        if path_index in overrides:
            bucket = overrides[path_index]
            ex.overridden_indices.add(path_index)
        elif path_index in cotes:
            ex.cote_paths.append(path)
            continue
        else:
            bucket = classify_path(path, pt_per_m)
            if bucket == "dashed":
                # A human override above takes the path whole; only the
                # classifier's own verdict is second-guessed piece by piece.
                for piece, piece_bucket in unfuse(path, pt_per_m):
                    _file_in_bucket(ex, piece, piece_bucket)
                continue
        _file_in_bucket(ex, path, bucket)
    return ex


def _draw_path(draw: ImageDraw.ImageDraw, path, scale: float, fill_it: bool,
               stroke_px: int) -> None:
    for item in path["items"]:
        kind = item[0]
        if kind == "re":
            r = item[1]
            box = [r.x0 * scale, r.y0 * scale, r.x1 * scale, r.y1 * scale]
            box = [min(box[0], box[2]), min(box[1], box[3]),
                   max(box[0], box[2]), max(box[1], box[3])]
            if fill_it:
                draw.rectangle(box, fill=255)
            else:
                draw.rectangle(box, outline=255, width=stroke_px)
        elif kind == "qu":
            q = item[1]
            pts = [(p.x * scale, p.y * scale) for p in (q.ul, q.ur, q.lr, q.ll)]
            if fill_it:
                draw.polygon(pts, fill=255)
            else:
                draw.line(pts + [pts[0]], fill=255, width=stroke_px)
        elif kind == "l":
            p1, p2 = item[1], item[2]
            draw.line([p1.x * scale, p1.y * scale, p2.x * scale, p2.y * scale],
                      fill=255, width=stroke_px)
        elif kind == "c":
            p0, c1, c2, p3 = item[1], item[2], item[3], item[4]
            prev = (p0.x, p0.y)
            for i in range(1, 9):
                t = i / 8
                x = ((1 - t) ** 3 * p0.x + 3 * (1 - t) ** 2 * t * c1.x
                     + 3 * (1 - t) * t ** 2 * c2.x + t ** 3 * p3.x)
                y = ((1 - t) ** 3 * p0.y + 3 * (1 - t) ** 2 * t * c1.y
                     + 3 * (1 - t) * t ** 2 * c2.y + t ** 3 * p3.y)
                draw.line([prev[0] * scale, prev[1] * scale, x * scale, y * scale],
                          fill=255, width=stroke_px)
                prev = (x, y)
    # filled polygons made of line segments (walls are often 'l' loops)
    if fill_it:
        pts = [(x * scale, y * scale) for x, y in _path_points(path)]
        if len(pts) >= 3:
            draw.polygon(pts, fill=255)


def door_seal_mask(door_arc_paths, page_rect: fitz.Rect, dpi: int,
                   stroke_px: int = 3) -> np.ndarray:
    """A thin barrier line across each detected door swing, not its bbox.

    Used only to seal room boundaries at doorways during segmentation
    (connected components): a door opening is a real room-to-room
    boundary for that purpose even though its floor stays usable for the
    Ø1.50 rotation circle (that circle-fitting exclusion is the separate
    include_door_arcs mechanism). The seal is the arc's two radii, hinge
    to each end: one end is the leaf closed, so hinge-to-it *is* the
    doorway, jamb to jamb; the other is the leaf open, a line with a free
    end that parts nothing on its own -- so neither end need be told
    apart. The chord between the two ends was the seal once, and cut
    across the swing instead of the doorway: the wedge between chord and
    doorway stayed open to both rooms, and a WC fused with the couloir
    its door opens onto. Filling the whole bbox instead of thin lines
    was tried and rejected: it can be large enough relative to a small
    room to erase that room's entire seed.
    """
    scale = dpi / 72.0
    w, h = int(page_rect.width * scale), int(page_rect.height * scale)
    img = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(img)
    for path in door_arc_paths:
        curve_items = [it for it in path["items"] if it[0] == "c"]
        if not curve_items:
            continue
        start, end = curve_items[0][1], curve_items[-1][4]
        hx, hy = _arc_hinge(start, end, curve_items)
        for tip in (start, end):
            # Run a stroke past each end: the arc stops on the jamb's face,
            # and rasterising can leave a pixel of floor between them.
            dx, dy = tip.x - hx, tip.y - hy
            k = 2 * stroke_px / (scale * max((dx * dx + dy * dy) ** 0.5, 1e-6))
            draw.line([(hx - k * dx) * scale, (hy - k * dy) * scale,
                       (tip.x + k * dx) * scale, (tip.y + k * dy) * scale],
                      fill=255, width=stroke_px)
    return np.array(img) > 0


def _arc_hinge(start, end, curve_items) -> tuple[float, float]:
    """The centre of a door's quarter-circle swing: of the two points that
    see `start` and `end` at a right angle, the one away from the arc."""
    mx, my = (start.x + end.x) / 2, (start.y + end.y) / 2
    hx, hy = (end.y - start.y) / 2, (start.x - end.x) / 2
    # A point on the arc itself: its middle control points bulge its way.
    c = curve_items[len(curve_items) // 2]
    bx, by = (c[2].x + c[3].x) / 2, (c[2].y + c[3].y) / 2
    a, b = (mx + hx, my + hy), (mx - hx, my - hy)
    return max(a, b, key=lambda p: (p[0] - bx) ** 2 + (p[1] - by) ** 2)


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Andrew's monotone chain, counter-clockwise."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def half(seq):
        out: list[tuple[float, float]] = []
        for q in seq:
            while len(out) >= 2:
                (x1, y1), (x2, y2) = out[-2], out[-1]
                if (x2 - x1) * (q[1] - y1) - (y2 - y1) * (q[0] - x1) > 0:
                    break
                out.pop()
            out.append(q)
        return out

    return half(pts)[:-1] + half(reversed(pts))[:-1]


def rasterize_placards(paths, page_rect: fitz.Rect, dpi: int) -> np.ndarray:
    """A placard blocks as a **solid**, not as its linework (docs/adr/0012).

    rasterize_paths cannot do this: _draw_path only honours `fill` for "re"
    and "qu" items, and a placard is drawn as bare "l" segments, so filling it
    there still leaves a dashed outline the circle can creep between. Filling
    the convex hull says what is meant -- the placard is not floor -- and costs
    nothing on an axis-aligned symbol, where the hull *is* the bounding box,
    while staying correct on a plan drawn at an angle, where a bbox would
    overshoot into real floor.
    """
    return _fill_hulls(paths, page_rect, dpi)


def _fill_hulls(paths, page_rect: fitz.Rect, dpi: int) -> np.ndarray:
    """Fill each path's convex hull solid -- a fixture drawn as one symbol."""
    scale = dpi / 72.0
    w, h = int(page_rect.width * scale), int(page_rect.height * scale)
    img = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(img)
    for path in paths:
        hull = _convex_hull(_path_points(path))
        if len(hull) >= 3:
            draw.polygon([(x * scale, y * scale) for x, y in hull], fill=255)
    return np.array(img) > 0


def _draw_cell_side(draw: ImageDraw.ImageDraw, item, scale: float,
                    seg_min: float) -> None:
    """Draw one item of an appliance's linework if it can be a side of its
    cell: a straight axis-aligned stroke too long to be lettering, or a
    rectangle item -- an évier's outline is drawn as one."""
    kind = item[0]
    if kind == "l":
        a, b = item[1], item[2]
        if math.hypot(b.x - a.x, b.y - a.y) < seg_min:
            return
        if abs(a.x - b.x) > FIXTURE_AXIS_TOL_PT \
                and abs(a.y - b.y) > FIXTURE_AXIS_TOL_PT:
            return
        draw.line([a.x * scale, a.y * scale, b.x * scale, b.y * scale],
                  fill=255, width=2)
    elif kind == "re":
        r = item[1]
        draw.rectangle([min(r.x0, r.x1) * scale, min(r.y0, r.y1) * scale,
                        max(r.x0, r.x1) * scale, max(r.y0, r.y1) * scale],
                       outline=255, width=2)
    elif kind == "qu":
        q = item[1]
        pts = [(p.x * scale, p.y * scale) for p in (q.ul, q.ur, q.lr, q.ll)]
        draw.line(pts + [pts[0]], fill=255, width=2)


def is_toilet(path, pt_per_m: float) -> bool:
    """A toilet's footprint: a dark symbol of a toilet's size, longer than it is wide
    (docs/adr/0015). Shape only -- which bucket to look in is the caller's."""
    if _grey(path.get("color")) > STROKE_MAX_GREY:
        return False
    r = path["rect"]
    short, long_ = sorted((r.width / pt_per_m, r.height / pt_per_m))
    return (TOILET_SHORT_MIN_M <= short <= TOILET_SHORT_MAX_M
            and TOILET_LONG_MIN_M <= long_ <= TOILET_LONG_MAX_M
            and long_ >= TOILET_ELONGATION_MIN * short)


def toilet_mask(ex: PlanExtract, dpi: int) -> np.ndarray:
    """Every toilet on the page, filled solid by its hull (docs/adr/0015).

    Candidates come from the decor bucket, where the bowl's short strokes put
    them, and a path a human bucketed is held to that ruling, as
    fixture_cell_mask holds it. The path stays in `dashed_paths`, so the
    sanitary rung still finds it there once the room is typed.
    """
    wcs = [p for p in ex.dashed_paths
           if p["path_index"] not in ex.overridden_indices
           and not is_dashed_closed_shape(p)
           and is_toilet(p, ex.pt_per_m)]
    return _fill_hulls(wcs, ex.page_rect, dpi)


def _mark_appliance_shaped(out: np.ndarray, labels: np.ndarray, stats,
                           px_per_m: float) -> None:
    """Mark in `out` every labelled component that measures like an
    appliance, filled out to its outer boundary: whatever is drawn inside it
    -- a basin, a hob's circles, an "F" -- goes with it."""
    short_min = FIXTURE_SHORT_MIN_M * px_per_m
    short_max = FIXTURE_SHORT_MAX_M * px_per_m
    long_max = FIXTURE_LONG_MAX_M * px_per_m
    for i in range(1, len(stats)):
        x, y, cw, ch, _ = stats[i]
        if not (short_min <= min(cw, ch) <= short_max
                and max(cw, ch) <= long_max):
            continue
        own = (labels[y:y + ch, x:x + cw] == i).astype(np.uint8)
        outline, _ = cv2.findContours(own, cv2.RETR_EXTERNAL,
                                      cv2.CHAIN_APPROX_SIMPLE)
        solid = np.zeros_like(own)
        cv2.drawContours(solid, outline, -1, 1, thickness=cv2.FILLED)
        if solid.sum() >= FIXTURE_RECT_MIN * cw * ch:
            out[y:y + ch, x:x + cw] |= solid > 0


def fixture_cell_mask(ex: PlanExtract, blocked: np.ndarray,
                      dpi: int) -> np.ndarray:
    """Every appliance cell on the page, filled solid (docs/adr/0014).

    `blocked` is what already bounds free space -- walls, partition lines,
    obstacles, placards. The dark straight strokes of the decor bucket are
    added to it *only to find cells*: they close each appliance box off from
    the room it stands in, and the components that come out small and
    rectangular are the appliances. None of that linework is returned, so a
    bed or a wardrobe drawn in the same strokes is left exactly as it was.

    A cell is judged by its outer boundary. What is drawn inside it -- the
    "F", the hob's circles, the basin of an évier -- is filled with it.

    The pixel kernels below are tied to the 2 px stroke every rasterizer in
    this module draws, not to the plan, so they are written in pixels.
    """
    scale = dpi / 72.0
    h, w = blocked.shape
    px_per_m = ex.pt_per_m * scale
    seg_min = FIXTURE_SEG_MIN_M * ex.pt_per_m

    img = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(img)
    for path in ex.dashed_paths:
        # A human's bucket is a ruling, as pipeline._promote_sanitary_obstacles
        # reads it: a path they called decor does not wall a cell in.
        if path["path_index"] in ex.overridden_indices:
            continue
        if _grey(path.get("color")) > STROKE_MAX_GREY:
            continue
        # A dashed closed shape -- a clearance zone -- is closed by its
        # dashes as a box is by its sides, and is never a fixture.
        if is_dashed_closed_shape(path):
            continue
        for item in path["items"]:
            _draw_cell_side(draw, item, scale, seg_min)
    k = max(3, round(FIXTURE_GAP_CLOSE_M * px_per_m)) | 1
    ink = cv2.morphologyEx((np.array(img) > 0).astype(np.uint8),
                           cv2.MORPH_CLOSE, np.ones((k, k), np.uint8)) > 0

    cells = np.zeros((h, w), bool)
    free = (~(blocked | ink)).astype(np.uint8)
    _, labels, stats, _ = cv2.connectedComponentsWithStats(free, connectivity=4)
    _mark_appliance_shaped(cells, labels, stats, px_per_m)

    # Hatching the closing made solid is an appliance in its own right when it
    # has an appliance's outline -- an évier whose drainer, basin rim and sides
    # all closed into one block, leaving no free cell big enough to count. A
    # door leaf is solid too, and 5 cm wide, so it never has that outline.
    solid_ink = cv2.morphologyEx(ink.astype(np.uint8), cv2.MORPH_OPEN,
                                 np.ones((3, 3), np.uint8))
    _, ink_labels, ink_stats, _ = cv2.connectedComponentsWithStats(
        solid_ink, connectivity=8)
    _mark_appliance_shaped(cells, ink_labels, ink_stats, px_per_m)
    if not cells.any():
        return cells

    # Any other solid hatching belongs to the appliance it touches -- a drainer
    # beside a basin cell -- and to nothing else.
    near = cv2.dilate(cells.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    touching = np.unique(ink_labels[near])
    fixture = cells | np.isin(ink_labels, touching[touching > 0])
    # ...and the outline strokes themselves, which lie in no cell.
    fixture = cv2.dilate(fixture.astype(np.uint8),
                         np.ones((5, 5), np.uint8)) > 0

    # A hole enclosed by fixture alone is inside an appliance: the basin.
    hn, holes, hole_stats, _ = cv2.connectedComponentsWithStats(
        (~fixture).astype(np.uint8), connectivity=4)
    edge = set(np.unique(np.concatenate(
        [holes[0], holes[-1], holes[:, 0], holes[:, -1]])).tolist())
    hole_max = FIXTURE_HOLE_MAX_M2 * px_per_m ** 2
    inside = [i for i in range(1, hn)
              if i not in edge and hole_stats[i][4] < hole_max]
    return fixture | np.isin(holes, inside)


def rasterize_paths(paths, page_rect: fitz.Rect, dpi: int, fill: bool,
                    stroke_px: int = 2) -> np.ndarray:
    scale = dpi / 72.0
    w, h = int(page_rect.width * scale), int(page_rect.height * scale)
    img = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(img)
    for path in paths:
        _draw_path(draw, path, scale, fill, stroke_px)
    return np.array(img) > 0
