"""Rooms with outlines in metres: drawn walls on a vector PDF, SAM 3.1 on a picture.

On a vector PDF each room Muse Spark labelled grows from its label out to the drawn walls
(geometry.segment_seeded), clipped to the region the walls alone close off
(geometry.segment_rooms), so a doorway no arc seals cannot let it run into the next room.
Floor no label reaches is cut by the walls alone and typed by the name written in it, a
toilet drawn in it, or Muse Spark looking at the whole plan with those rooms numbered.

A plan with no vector walls -- a scan, a photo -- is a picture: SAM 3.1 segments each label
point, and the scale comes from a dimension Muse Spark reads, or the written areas.
"""

from __future__ import annotations

import io
import math
import re
import statistics
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import pymupdf
from PIL import Image, ImageDraw, ImageFont

from conformscope import extract, geometry
from conformscope.fixtures import MeasuredFixture, assign_rooms, split_fixtures
from conformscope.labels import Dimension, RoomLabel, RoomReading, read_dimension, type_rooms
from conformscope.plan import Plan
from conformscope.segment import point_prompt, segment

# A sheet at 1:1 has this many PDF points per metre; at 1:100, a hundredth of it.
PT_PER_M_AT_1_TO_1 = 72 / 0.0254
DPI = 150                 # the grid the walls are rasterised and the rooms grown on
MIN_WALL_PATHS = 10       # fewer drawn walls than this and the plan is a picture
SCALE_TOLERANCE = 0.05    # dimension lines and the written scale may disagree this much
SEED_HALF_M = 0.4         # a label point becomes a seed square this far either side
CLIP_M = 0.3              # how far a room may run past the region the walls close off
SAME_ROOM_SHARE = 0.5     # a walls-only region this much inside a labelled room is that room
MIN_WIDTH_M = 0.6         # narrower than this is a shaft or a gap, not a room
SIMPLIFY_M = 0.02         # outline tolerance
SANITARY = {"wc", "bathroom"}

TYPE_WORDS = [
    ("living", r"sejour|salon|living|piece (de vie|a vivre)"),
    ("kitchen", r"cuisine|kitchen(ette)?"),
    ("bathroom", r"sdb|sde|salle de bains?|salle d.eau|bathroom|shower|douche"),
    ("wc", r"wc|toilettes?|toilet"),
    ("bedroom", r"chambre|bedroom"),
    ("corridor", r"degagement|dgt|couloir|circulation|corridor|hall"),
    ("entrance", r"entree|entrance"),
    ("storage", r"pl|placard|rangement|cellier|storage|dressing"),
]


@dataclass
class MeasuredRoom:
    name: str
    room_type: str
    type_source: str                     # "text" | "fixture" | "muse" | "none"
    area_m2: float | None
    written_area_m2: float | None
    polygon_px: list[tuple[float, float]]  # on the plan image
    polygon_m: list[tuple[float, float]]   # from the plan's top-left corner, y down
    circle_m: float | None               # diameter of the largest circle the free floor holds
    circle_px: tuple[float, float] | None
    warnings: list[str] = field(default_factory=list)
    outline_source: str = "auto"  # "auto" | "merged" | "wall" (issue #6)
    fixtures: list[int] = field(default_factory=list)  # indices into RoomsResult.fixtures


@dataclass
class RoomsResult:
    kind: str                            # "vector" | "picture"
    scale_source: str | None             # "measured" | "scale" | "assumed" | "cote" | "from_areas"
    px_per_m: float | None               # plan image pixels per metre
    rooms: list[MeasuredRoom]
    warnings: list[str]
    fixtures: list[MeasuredFixture] = field(default_factory=list)


def scale_pt_per_m(text: str | None) -> float | None:
    """'1:100' (or 1/100, 1.100) as PDF points per metre of building."""
    match = re.search(r"1\s*[:/.]\s*(\d+)", text or "")
    if not match or int(match.group(1)) == 0:
        return None
    return PT_PER_M_AT_1_TO_1 / int(match.group(1))


def type_from_name(name: str) -> str | None:
    plain = unicodedata.normalize("NFKD", name.lower()).encode("ascii", "ignore").decode()
    for room_type, words in TYPE_WORDS:
        if re.search(rf"\b({words})\b", plain):
            return room_type
    return None


def resolve_type(name_type: str | None, has_toilet: bool,
                 muse_type: str | None) -> tuple[str, str, list[str]]:
    """The written name, then a drawn toilet, then Muse Spark: (type, source, warnings)."""
    if name_type:
        return name_type, "text", []
    if has_toilet:
        if muse_type in SANITARY:
            return muse_type, "fixture", []
        warnings = [f"A toilet is drawn here, but Muse Spark read it as {muse_type}"] if muse_type else []
        return "wc", "fixture", warnings
    if muse_type:
        return muse_type, "muse", []
    return "other", "none", []


def picture_px_per_m(dimension: Dimension | None, labels: list[RoomLabel],
                     mask_px: list[int]) -> tuple[float | None, str | None]:
    """A picture's scale: a written dimension, else the median over the written areas."""
    if dimension and dimension.value_m > 0:
        length = math.hypot(dimension.x2 - dimension.x1, dimension.y2 - dimension.y1)
        if length > 0:
            return length / dimension.value_m, "cote"
    ratios = [math.sqrt(px / label.area_m2) for label, px in zip(labels, mask_px)
              if label.area_m2 and px > 0]
    if len(ratios) >= 2:
        return statistics.median(ratios), "from_areas"
    return None, None


_AREA = re.compile(r"(\d+(?:[.,]\d+)?)\s*m(?:²|2)")
_NUMBER = re.compile(r"\d+[.,]\d+")


def _is_area_unit(text: str) -> bool:
    # "m²", "m2", or an "m" whose ² the PDF's font encoding turned into something else.
    return text in ("m²", "m2") or (len(text) == 2 and text[0] == "m" and not text[1].isalnum())


def written_areas(words) -> list[tuple[float, float, float]]:
    """Areas printed on a vector plan: (m², x, y of the number in PDF points).

    A number followed by m² is an area; one followed by a bare "m" is a dimension.
    """
    found = []
    for i, w in enumerate(words):
        text = w[4]
        inline = _AREA.fullmatch(text)
        if inline:
            value = inline.group(1)
        elif _NUMBER.fullmatch(text) and i + 1 < len(words) and _is_area_unit(words[i + 1][4]):
            value = text
        else:
            continue
        found.append((float(value.replace(",", ".")), (w[0] + w[2]) / 2, (w[1] + w[3]) / 2))
    return found


def outline(crop: np.ndarray, origin: tuple[int, int], px_per_m: float,
            to_plan: float) -> tuple[list, list, float]:
    """A room's mask as (polygon on the plan image, polygon in metres, area in m²).

    `crop` is the mask over its own extent, `origin` where it sits on the grid it was
    grown on, and `to_plan` that grid's pixels in plan-image pixels.
    """
    padded = np.pad(crop.astype(np.uint8), 1)
    contours, _ = cv2.findContours(padded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contour = max(contours, key=cv2.contourArea)
    contour = cv2.approxPolyDP(contour, max(SIMPLIFY_M * px_per_m, 1.0), True)
    points = [(float(x - 1 + origin[0]), float(y - 1 + origin[1])) for x, y in contour[:, 0]]
    polygon_px = [(round(x * to_plan, 1), round(y * to_plan, 1)) for x, y in points]
    polygon_m = [(round(x / px_per_m, 3), round(y / px_per_m, 3)) for x, y in points]
    return polygon_px, polygon_m, float(crop.sum()) / px_per_m ** 2


def _crop(mask: np.ndarray) -> tuple[tuple[int, int], np.ndarray]:
    ys, xs = np.nonzero(mask)
    x0, y0 = int(xs.min()), int(ys.min())
    return (x0, y0), mask[y0:int(ys.max()) + 1, x0:int(xs.max()) + 1]


def _circle(free: np.ndarray, origin: tuple[int, int], px_per_m: float) -> tuple[float, tuple]:
    """Diameter in metres and centre (on the grid) of the largest circle `free` holds."""
    if not free.any():
        return 0.0, origin
    h, w = free.shape
    radius_m, (cx, cy) = geometry._fit_circle(free, (0, 0, w - 1, h - 1), px_per_m)
    return 2 * radius_m, (cx + origin[0], cy + origin[1])


def _disk(radius_px: int) -> np.ndarray:
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius_px + 1, 2 * radius_px + 1))


def measure_rooms(client, path: str | Path, plan: Plan, reading: RoomReading, corrections=None) -> RoomsResult:
    if Path(path).suffix.lower() == ".pdf":
        with pymupdf.open(path) as doc:
            result = vector_rooms(client, doc, plan, reading, corrections or [])
        if result is not None:
            return result
    return picture_rooms(client, plan, reading)


# --- vector PDFs ------------------------------------------------------------------------


def _calibrate(doc, reading: RoomReading):
    ex = extract.extract_plan(doc)
    stated = scale_pt_per_m(reading.scale)
    if ex.calibration_provenance == "measured":
        warnings = []
        if stated and abs(ex.pt_per_m - stated) / stated > SCALE_TOLERANCE:
            warnings.append(
                f"The dimension lines give {ex.pt_per_m:.2f} pt/m but the plan says "
                f"{reading.scale} ({stated:.2f} pt/m); using the dimension lines")
        return ex, "measured", warnings
    if stated:
        return extract.extract_plan(doc, pt_per_m_override=stated), "scale", []
    return ex, "assumed", [f"No dimension line or written scale was read; {ex.calibration_note}"]


def _toilet_points(ex, dpi: int) -> list[tuple[int, int]]:
    s = dpi / 72
    return [(int((p["rect"].x0 + p["rect"].x1) / 2 * s), int((p["rect"].y0 + p["rect"].y1) / 2 * s))
            for p in ex.dashed_paths
            if not extract.is_dashed_closed_shape(p) and extract.is_toilet(p, ex.pt_per_m)]


def _sanitary_fixtures(ex, mask: np.ndarray, dpi: int) -> np.ndarray:
    """Dashed equipment inside a WC or bathroom (sink, washing machine) blocks its circle."""
    s = dpi / 72
    inside = []
    for p in ex.dashed_paths:
        if extract.is_roundish(p) or extract.is_dashed_closed_shape(p):
            continue
        cx = int((p["rect"].x0 + p["rect"].x1) / 2 * s)
        cy = int((p["rect"].y0 + p["rect"].y1) / 2 * s)
        if 0 <= cy < mask.shape[0] and 0 <= cx < mask.shape[1] and mask[cy, cx]:
            inside.append(p)
    if not inside:
        return np.zeros_like(mask)
    return extract.rasterize_paths(inside, ex.page_rect, dpi, fill=False, stroke_px=2)


def _name_in(mask: np.ndarray, words, dpi: int) -> str:
    s = dpi / 72
    parts = []
    for w in words:
        text = w[4]
        if not text or not text[0].isalpha() or text.lower() in {"m", "m²", "rwdp", "scale", "n"}:
            continue
        cx, cy = int((w[0] + w[2]) / 2 * s), int((w[1] + w[3]) / 2 * s)
        if 0 <= cy < mask.shape[0] and 0 <= cx < mask.shape[1] and mask[cy, cx]:
            parts.append(text)
    return " ".join(parts)


def _numbered_plan(plan: Plan, rooms: list[tuple[int, list, tuple[float, float]]]) -> bytes:
    """The plan with each room to type outlined and numbered, for one Muse Spark call."""
    image = Image.open(io.BytesIO(plan.png)).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=max(18, plan.width // 60))
    for number, polygon, (cx, cy) in rooms:
        draw.polygon(polygon, outline=(0, 120, 255), width=3)
        draw.text((cx, cy), str(number), fill=(220, 0, 0), font=font, anchor="mm",
                  stroke_width=2, stroke_fill=(255, 255, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def vector_rooms(client, doc, plan: Plan, reading: RoomReading, corrections=None) -> RoomsResult | None:
    """Rooms cut by the drawn walls, or None when the PDF has too few to be a vector plan."""
    ex, scale_source, warnings = _calibrate(doc, reading)
    if len(ex.wall_paths) + len(ex.wall_line_paths) < MIN_WALL_PATHS:
        return None
    rect = ex.page_rect
    px_per_m = ex.pt_per_m * DPI / 72
    to_plan = plan.width / (rect.width * DPI / 72)

    wall = extract.rasterize_paths(ex.wall_paths, rect, DPI, fill=True)
    barrier = extract.rasterize_paths(ex.wall_line_paths, rect, DPI, fill=False, stroke_px=2)
    # Issue #6: walls drawn by hand join the barrier before the cut, overshot
    # by 0.15 m at each end so a click just short still closes the gap.
    corrections = list(corrections or [])
    drawn = np.zeros(wall.shape, np.uint8)
    for corr in corrections:
        kind = corr.get("kind") if isinstance(corr, dict) else getattr(corr, "kind", None)
        if kind not in ("wall", "drawn_wall"):
            continue
        start = corr["start"] if isinstance(corr, dict) else corr.start
        end = corr["end"] if isinstance(corr, dict) else corr.end
        ax, ay = float(start[0]) * DPI / 72, float(start[1]) * DPI / 72
        bx, by = float(end[0]) * DPI / 72, float(end[1]) * DPI / 72
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        if length == 0:
            continue
        over = 0.15 * px_per_m
        ax, ay = ax - dx / length * over, ay - dy / length * over
        bx, by = bx + dx / length * over, by + dy / length * over
        cv2.line(drawn, (round(ax), round(ay)), (round(bx), round(by)), 1, thickness=2)
    if drawn.any():
        barrier = barrier | drawn.astype(bool)
    obstacles = extract.rasterize_paths(ex.obstacle_paths, rect, DPI, fill=False, stroke_px=2) & ~wall
    placards = extract.rasterize_placards(ex.placard_paths, rect, DPI) & ~wall
    cells = extract.fixture_cell_mask(ex, wall | barrier | obstacles | placards, DPI) & ~wall
    toilet_pixels = extract.toilet_mask(ex, DPI) & ~wall
    obstacles |= placards | cells | toilet_pixels
    fixtures = split_fixtures(placards, cells, toilet_pixels)
    doors = extract.door_seal_mask(ex.door_arc_paths, rect, DPI)
    # Furniture blocks the turning circle, never the room: a label printed on a drawn bed
    # must still grow into the whole bedroom, and a written area counts the floor under it.
    no_obstacles = np.zeros_like(wall)

    half = SEED_HALF_M * px_per_m
    points = [(label.x / to_plan, label.y / to_plan) for label in reading.rooms]
    squares = [[(x - half, y - half), (x + half, y - half), (x + half, y + half), (x - half, y + half)]
               for x, y in points]
    _, _, seeded = geometry.segment_seeded(wall, barrier, no_obstacles, px_per_m, squares,
                                           door_mask=doors)
    _, _, walls_only = geometry.segment_rooms(wall, barrier, no_obstacles, px_per_m,
                                              door_mask=doors)
    clip = _disk(int(CLIP_M * px_per_m))

    # (mask, name, name type, written area) for every room, labelled ones first.
    found = []
    claimed = np.zeros_like(wall)
    for label, (x, y) in zip(reading.rooms, points):
        x, y = int(x), int(y)
        grown = next((r for r in seeded if r.contains(x, y)), None)
        if grown is None:
            warnings.append(f"No room could be grown from the label {label.name!r}")
            continue
        mask = grown.full_mask()
        region = next((r for r in walls_only if r.contains(x, y)), None)
        if region is not None:
            mask &= cv2.dilate(region.full_mask().astype(np.uint8), clip).astype(bool)
        mask &= ~claimed
        if not mask.any():
            continue
        claimed |= mask
        found.append((mask, label.name, type_from_name(label.name) or label.room_type, label.area_m2, "auto"))

    spare = []  # floor too small to be a room, still claimable by a merge (issue #6)
    for region in walls_only:
        whole = region.full_mask()
        if (whole & claimed).sum() > SAME_ROOM_SHARE * whole.sum():
            continue
        mask = whole & ~claimed
        if mask.sum() / px_per_m ** 2 < geometry.MIN_ROOM_M2:
            spare.append(mask)
            continue
        origin, crop = _crop(mask)
        if _circle(crop, origin, px_per_m)[0] < MIN_WIDTH_M:
            spare.append(mask)
            continue
        name = _name_in(mask, ex.text_words, DPI)
        found.append((mask, name, type_from_name(name), None, "auto"))

    # Issue #6: replay merges. Points are PDF points, never room numbers:
    # rooms reshuffle on every re-cut, a point inside a room does not.
    def _grid(pt):
        return round(float(pt[0]) * DPI / 72), round(float(pt[1]) * DPI / 72)

    for corr in corrections:
        kind = corr.get("kind") if isinstance(corr, dict) else getattr(corr, "kind", None)
        if kind != "merge":
            continue
        point = corr["point"] if isinstance(corr, dict) else corr.point
        target = corr["target_point"] if isinstance(corr, dict) else corr.target_point
        gx, gy = _grid(point)
        tx, ty = _grid(target)
        region_i = next((i for i, f in enumerate(found)
                         if 0 <= gy < f[0].shape[0] and 0 <= gx < f[0].shape[1] and f[0][gy, gx]), None)
        target_i = next((i for i, f in enumerate(found)
                         if 0 <= ty < f[0].shape[0] and 0 <= tx < f[0].shape[1] and f[0][ty, tx]), None)
        if region_i is None and target_i is not None:
            # Unclaimed floor (or a sliver) can be claimed too, not just rooms.
            spare_i = next((i for i, m in enumerate(spare)
                            if 0 <= gy < m.shape[0] and 0 <= gx < m.shape[1] and m[gy, gx]), None)
            if spare_i is not None:
                m, n, t, w, _src = found[target_i]
                found[target_i] = (m | spare[spare_i], n, t, w, "merged")
                del spare[spare_i]
            continue
        if region_i is None or target_i is None or region_i == target_i:
            continue
        m, n, t, w, _src = found[target_i]
        found[target_i] = (m | found[region_i][0], n, t, w, "merged")
        del found[region_i]
    if drawn.any():
        near = cv2.dilate(drawn, _disk(max(1, int(0.3 * px_per_m)))).astype(bool)
        found = [(m, n, t, w, "wall" if s == "auto" and (m & near).any() else s)
                 for m, n, t, w, s in found]

    toilets = _toilet_points(ex, DPI)
    # The area printed in a room is what the architect wrote; Muse Spark's reading of it is
    # the fallback for a plan whose text is outlined rather than kept as text.
    s = DPI / 72
    printed = [(a, int(x * s), int(y * s)) for a, x, y in written_areas(ex.text_words)]
    shapes = []
    for mask, name, name_type, written, outline_source in found:
        written = next((a for a, x, y in printed
                        if 0 <= y < mask.shape[0] and 0 <= x < mask.shape[1] and mask[y, x]), written)
        origin, crop = _crop(mask)
        polygon_px, polygon_m, area_m2 = outline(crop, origin, px_per_m, to_plan)
        has_toilet = any(mask[ty, tx] for tx, ty in toilets
                         if 0 <= ty < mask.shape[0] and 0 <= tx < mask.shape[1])
        _, (cx, cy) = _circle(crop, origin, px_per_m)  # a point well inside, for its number
        shapes.append((mask, name, name_type, written, polygon_px, polygon_m, area_m2, has_toilet,
                       (cx * to_plan, cy * to_plan), outline_source))

    # One Muse Spark call types every room the plan does not name.
    to_type = [i for i, shape in enumerate(shapes) if shape[2] is None]
    muse_types: dict[int, str] = {}
    if to_type:
        png = _numbered_plan(plan, [(n, shapes[i][4], shapes[i][8])
                                    for n, i in enumerate(to_type, start=1)])
        try:
            _, by_number = type_rooms(client, png)
            muse_types = {to_type[n - 1]: t for n, t in by_number.items() if 1 <= n <= len(to_type)}
        except Exception as error:
            warnings.append(f"Muse Spark could not type the unnamed rooms: {error}")

    rooms = []
    for i, (mask, name, name_type, written, polygon_px, polygon_m, area_m2, has_toilet, _, outline_source) in enumerate(shapes):
        room_type, source, room_warnings = resolve_type(name_type, has_toilet, muse_types.get(i))
        blocked = obstacles | wall | barrier
        if room_type in SANITARY:
            blocked = blocked | _sanitary_fixtures(ex, mask, DPI)
        origin, crop = _crop(mask)
        h, w = crop.shape
        free = crop & ~blocked[origin[1]:origin[1] + h, origin[0]:origin[0] + w]
        circle_m, (cx, cy) = _circle(free, origin, px_per_m)
        rooms.append(MeasuredRoom(
            name=name, room_type=room_type, type_source=source, area_m2=round(area_m2, 2),
            written_area_m2=written, polygon_px=polygon_px, polygon_m=polygon_m,
            circle_m=round(circle_m, 2), circle_px=(round(cx * to_plan, 1), round(cy * to_plan, 1)),
            warnings=room_warnings, outline_source=outline_source))

    assign_rooms(fixtures, [shape[0] for shape in shapes], [room.room_type for room in rooms])
    measured = []
    for fixture in fixtures:
        polygon_px, polygon_m, _ = outline(fixture.crop, fixture.origin, px_per_m, to_plan)
        if fixture.room is not None:
            rooms[fixture.room].fixtures.append(len(measured))
        measured.append(MeasuredFixture(fixture.kind, fixture.room, polygon_px, polygon_m))
    return RoomsResult("vector", scale_source, px_per_m * to_plan, rooms, warnings, measured)


# --- pictures ---------------------------------------------------------------------------


def picture_rooms(client, plan: Plan, reading: RoomReading) -> RoomsResult:
    """Rooms from SAM 3.1 masks, one per Muse Spark label point."""
    warnings = ["This plan is a picture with no drawn walls, so its rooms come from SAM 3.1"]
    if not reading.rooms:
        return RoomsResult("picture", None, None, [], warnings + ["No room labels were read"])
    try:
        _, masks = segment(client, plan, point_prompt(reading.rooms, plan.width, plan.height))
    except Exception as error:
        warnings.append(f"SAM 3.1 could not segment the rooms: {error}")
        masks = []
    by_id = {str(m.object_id): m for m in masks}
    found = [(label, by_id.get(str(i))) for i, label in enumerate(reading.rooms)]
    found = [(label, m) for label, m in found if m is not None and m.bits.any()]

    try:
        _, dimension = read_dimension(client, plan)
    except Exception:
        dimension = None
    px_per_m, source = picture_px_per_m(dimension, [label for label, _ in found],
                                        [int(m.bits.sum()) for _, m in found])
    if px_per_m is None and found:
        warnings.append("No written dimension or room areas to scale this picture by; "
                        "enter one known dimension by hand")

    rooms = []
    for label, m in found:
        polygon_px, polygon_m, area_m2 = outline(m.bits, (m.left, m.top), px_per_m or 1.0, 1.0)
        circle = _circle(m.bits, (m.left, m.top), px_per_m) if px_per_m else None
        rooms.append(MeasuredRoom(
            name=label.name, room_type=type_from_name(label.name) or label.room_type,
            type_source="text", area_m2=round(area_m2, 2) if px_per_m else None,
            written_area_m2=label.area_m2, polygon_px=polygon_px,
            polygon_m=polygon_m if px_per_m else [],
            circle_m=round(circle[0], 2) if circle else None,
            circle_px=(float(circle[1][0]), float(circle[1][1])) if circle else None))
    return RoomsResult("picture", source, px_per_m, rooms, warnings)
