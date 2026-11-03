"""The PDF report for a dossier: what the auditor hands over once every sheet is reviewed.

Ported from pmr-checker's `api/report.py`. A **report** is built from the stored readings
only -- the same rooms, doors, walk and explanations the check screen shows, corrections
and overrides included -- so it never measures again and never calls a model. It opens
with the dossier at a glance (one line per sheet), then, for every sheet checked:

- the sheet annotated: rooms in their verdict colours, turning circles, doorways, stops;
- the rooms table, the doors too narrow, the walk, and Muse Spark's explanations when the
  auditor asked for them;
- a crop of the plan around every room whose turning circle fails.

A sheet never opened, or a plan annexe, is listed and not reported on. The table and text
are reportlab platypus; the annotated images are drawn with Pillow on the sheet's PNG.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (Image as RLImage, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

MARGIN = 1.6 * cm
CROP_PAD_PX = 40  # around a failing room's outline, so the crop shows its walls
REQUIRED_DIAMETER_M = 1.5

PASS = colors.Color(0.12, 0.55, 0.32)
PASS_BG = colors.Color(0.9, 0.97, 0.92)
FAIL = colors.Color(0.78, 0.22, 0.15)
FAIL_BG = colors.Color(1, 0.93, 0.92)
GREY = colors.Color(0.45, 0.5, 0.55)
INK = colors.Color(0.06, 0.11, 0.15)
RULE = colors.Color(0.86, 0.88, 0.9)

# The same palette on the images, as RGB.
_PASS = (31, 157, 92)
_FAIL = (216, 64, 44)
_GREY = (138, 151, 163)
_COBALT = (75, 131, 216)
_INK = (16, 28, 39)


@dataclass
class SheetReport:
    """One sheet of the dossier: its entry in dossier.json, its stored reading (None if it
    was never opened) and its PNG (None likewise)."""
    sheet: dict
    body: dict | None
    image: Image.Image | None


def build(title: str, sheets: list[SheetReport], today: date | None = None) -> bytes:
    styles = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=MARGIN, bottomMargin=MARGIN + 0.4 * cm,
                            leftMargin=MARGIN, rightMargin=MARGIN,
                            title=f"ConformScope report: {title}", author="ConformScope")
    width = A4[0] - 2 * MARGIN

    story: list = [
        Paragraph("ConformScope · accessibility report", styles["eyebrow"]),
        Paragraph(escape(title), styles["Title"]),
        Paragraph(f"Generated on {(today or date.today()).isoformat()} from the reviewed "
                  "readings, corrections and overrides included.", styles["muted"]),
        Spacer(1, 0.5 * cm),
    ]
    checked = [s for s in sheets if s.body and s.body.get("checked")]
    if checked:
        ok = all(_sheet_passes(s.body) for s in checked)
        story.append(_banner(ok, "Every checked sheet passes" if ok
                             else "Some checks fail: see the sheets below", styles))
    else:
        story.append(Paragraph("No sheet has been checked yet.", styles["Heading2"]))
    story += [Spacer(1, 0.4 * cm), _dossier_table(sheets, styles, width), Spacer(1, 0.3 * cm)]

    for s in checked:
        story.append(PageBreak())
        story += _sheet_story(s, styles, width)

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


# ── the dossier at a glance ──────────────────────────────────────────────────────────

def _sheet_passes(body: dict) -> bool:
    rooms_ok = all(r.get("conforme") is not False for r in body.get("rooms", []))
    walk = body.get("walk") or {}
    walk_ok = not walk.get("stops") and not walk.get("unreachable")
    return rooms_ok and _doors_ok(body) is not False and body.get("accessible_wc") is not False and walk_ok


def _doors_ok(body: dict) -> bool | None:
    """Judged from the doors themselves, overrides included: None when none was checked."""
    judged = [d["ok"] for d in body.get("doors") or [] if d.get("ok") is not None]
    return all(judged) if judged else None


def _counts(body: dict) -> tuple[int, int]:
    judged = [r for r in body.get("rooms", []) if r.get("conforme") is not None]
    return sum(1 for r in judged if r["conforme"]), len(judged)


def _dossier_table(sheets: list[SheetReport], styles, width: float) -> Table:
    rows = [["Sheet", "Status", "Turning circle", "Doors", "WC", "Walk"]]
    style = _table_style()
    for i, s in enumerate(sheets, start=1):
        body = s.body
        if s.sheet.get("annexe"):
            rows.append([_p(s.sheet["name"], styles), "Plan annexe, not checked", "", "", "", ""])
            continue
        if not body or not body.get("checked"):
            rows.append([_p(s.sheet["name"], styles), "Not opened yet", "", "", "", ""])
            continue
        passing, judged = _counts(body)
        doors = body.get("doors") or []
        narrow = sum(1 for d in doors if d.get("ok") is False)
        walk = body.get("walk") or {}
        reached, total = len(walk.get("reached", [])), len(body.get("rooms", []))
        wc = body.get("accessible_wc")
        rows.append([
            _p(s.sheet["name"], styles),
            "Pass" if _sheet_passes(body) else "Fails",
            f"{passing}/{judged} rooms pass",
            "—" if _doors_ok(body) is None else ("All wide enough" if not narrow else f"{narrow} too narrow"),
            "—" if wc is None else ("Yes" if wc else "No"),
            f"{reached}/{total} rooms reached" if walk.get("route") else "—",
        ])
        _colour_cell(style, 1, i, _sheet_passes(body))
    table = Table(rows, colWidths=[w * width for w in (0.24, 0.12, 0.17, 0.16, 0.13, 0.18)], repeatRows=1)
    table.setStyle(TableStyle(style))
    return table


# ── one sheet ────────────────────────────────────────────────────────────────────────

def _sheet_story(s: SheetReport, styles, width: float) -> list:
    body = s.body or {}
    rooms = body.get("rooms", [])
    passing, judged = _counts(body)
    story: list = [Paragraph(escape(s.sheet["name"]), styles["Heading1"])]
    scale = body.get("scale") or "no written scale"
    source = body.get("scale_source")
    story.append(Paragraph(escape(f"Scale {scale}" + (f", {source.replace('_', ' ')}" if source else "")
                                  + f" · {len(rooms)} rooms measured"), styles["muted"]))
    story.append(Spacer(1, 0.25 * cm))
    story.append(_banner(_sheet_passes(body),
                         f"{passing}/{judged} rooms fit the Ø{REQUIRED_DIAMETER_M:.2f} m turning circle",
                         styles))
    story.append(Spacer(1, 0.3 * cm))

    if s.image is not None:
        annotated = annotate(s.image, body)
        story.append(_fit(annotated, width, 15 * cm))
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("Green: passes. Red: fails. Grey: not checked. Dashed rings are "
                               "the largest turning circle each room holds; lines are doorways; "
                               "red dots are where the wheelchair stops.", styles["muted"]))

    for warning in body.get("warnings", []):
        story.append(Paragraph(escape(f"Note: {warning}"), styles["note"]))

    story += [Spacer(1, 0.4 * cm), Paragraph("Rooms", styles["Heading2"]), _rooms_table(rooms, styles, width)]

    doors = body.get("doors") or []
    narrow = [d for d in doors if d.get("ok") is False]
    if _doors_ok(body) is not None:
        story += [Spacer(1, 0.4 * cm), Paragraph("Doors", styles["Heading2"])]
        judged_doors = [d for d in doors if d.get("ok") is not None]
        if not narrow:
            story.append(Paragraph(f"All {len(judged_doors)} doors checked are wide enough.", styles["Normal"]))
        else:
            story.append(_doors_table(narrow, rooms, styles, width))

    if body.get("accessible_wc") is not None:
        story += [Spacer(1, 0.4 * cm), Paragraph("Accessible WC", styles["Heading2"]),
                  Paragraph("A toilet has a 0.80 × 1.30 m transfer space beside it." if body["accessible_wc"]
                            else "No toilet has a 0.80 × 1.30 m transfer space beside it.", styles["Normal"])]

    walk = body.get("walk") or {}
    if walk.get("route"):
        story += [Spacer(1, 0.4 * cm), Paragraph("Walk the plan", styles["Heading2"]),
                  Paragraph(escape(walk.get("verdict", "")), styles["Normal"])]
        for stop in walk.get("stops", []):
            where = ("At a door" if stop.get("kind") == "door"
                     else _room_name(rooms, stop.get("room")))
            story.append(Paragraph(escape(f"• {where}: {stop.get('reason', '')}"), styles["Normal"]))
        if walk.get("unreachable"):
            names = ", ".join(_room_name(rooms, u["room"]) for u in walk["unreachable"])
            story.append(Paragraph(escape(f"Not reached: {names}"), styles["muted"]))

    explain = body.get("explain") or {}
    if explain.get("failures"):
        story += [Spacer(1, 0.4 * cm), Paragraph("Why it fails, and how to fix it", styles["Heading2"])]
        if explain.get("explained_by"):
            story.append(Paragraph(escape(f"Explained by {explain['explained_by']}"
                                          + (f", verified by {explain['verified_by']}" if explain.get("verified_by") else "")),
                                   styles["muted"]))
        for failure in explain["failures"]:
            story.append(KeepTogether(_failure(failure, styles)))

    failing = [(i, r) for i, r in enumerate(rooms) if r.get("conforme") is False]
    if failing and s.image is not None:
        story += [PageBreak(), Paragraph("Rooms that fail, on the plan", styles["Heading2"])]
        annotated = annotate(s.image, body)
        for i, room in failing:
            crop = _crop(annotated, room)
            caption = (f"{i + 1}. {_room_name(rooms, i)} — fails: free Ø"
                       f"{_m(room.get('max_diameter_m'))} m, needs Ø{REQUIRED_DIAMETER_M:.2f} m")
            story.append(KeepTogether([Paragraph(escape(caption), styles["Heading4"]),
                                       _fit(crop, width, 9 * cm), Spacer(1, 0.35 * cm)]))
    return story


def _rooms_table(rooms: list[dict], styles, width: float):
    if not rooms:
        return Paragraph("No rooms were measured on this sheet.", styles["muted"])
    rows = [["No.", "Room", "Type", "Area", "Free Ø", "Verdict"]]
    style = _table_style()
    for i, room in enumerate(rooms, start=1):
        ok = room.get("conforme")
        rows.append([str(i), _p(_room_name(rooms, i - 1), styles), room.get("room_type", ""),
                     f"{room['area_m2']:.1f} m²" if room.get("area_m2") is not None else "—",
                     f"{_m(room.get('max_diameter_m'))} m" if room.get("max_diameter_m") is not None else "—",
                     "Not checked" if ok is None else ("Pass" if ok else "Fails")])
        if ok is not None:
            _colour_cell(style, 5, i, ok)
    table = Table(rows, colWidths=[w * width for w in (0.07, 0.35, 0.15, 0.13, 0.13, 0.17)], repeatRows=1)
    table.setStyle(TableStyle(style))
    return table


def _doors_table(doors: list[dict], rooms: list[dict], styles, width: float) -> Table:
    rows = [["Between", "Role", "Width", "Needs", "Verdict"]]
    style = _table_style()
    for i, door in enumerate(doors, start=1):
        sides = " – ".join("outside" if r is None else _room_name(rooms, r) for r in door.get("rooms", []))
        rows.append([_p(sides, styles), door.get("role", ""), f"{door['width_m']:.2f} m",
                     f"{door['required_m']:.2f} m" if door.get("required_m") is not None else "—", "Too narrow"])
        _colour_cell(style, 4, i, False)
    table = Table(rows, colWidths=[w * width for w in (0.45, 0.14, 0.13, 0.13, 0.15)], repeatRows=1)
    table.setStyle(TableStyle(style))
    return table


def _failure(failure: dict, styles) -> list:
    verify = failure.get("verify") or {}
    if verify.get("status") == "verified":
        pct = round(100 * verify.get("confidence", 0))
        second = (f"Doubtful: the verifier {'is unsure' if verify.get('agree') else 'disagrees'} ({pct}%). "
                  f"{verify.get('note', '')}" if verify.get("doubtful") else f"Verified ({pct}%).")
    else:
        second = "Not verified."
    return [Paragraph(f"<b>{escape(failure.get('subject', ''))}</b>", styles["Normal"]),
            Paragraph(escape(failure.get("reason", "")), styles["Normal"]),
            Paragraph(f"<i>Fix: {escape(failure.get('fix', ''))}</i>", styles["Normal"]),
            Paragraph(escape(second), styles["muted"]), Spacer(1, 0.25 * cm)]


# ── the images ───────────────────────────────────────────────────────────────────────

def annotate(image: Image.Image, body: dict) -> Image.Image:
    """The sheet with its verdicts drawn on it, as the check screen draws them."""
    base = image.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    unit = max(base.size) / 200  # one mark size whatever the sheet's resolution
    rooms = body.get("rooms", [])
    px_per_m = body.get("px_per_m")

    for room in rooms:
        colour = _GREY if room.get("conforme") is None else (_PASS if room["conforme"] else _FAIL)
        polygon = [tuple(p) for p in room.get("polygon_px", [])]
        if len(polygon) >= 3:
            draw.polygon(polygon, fill=colour + (34,), outline=colour + (255,), width=max(2, round(unit * 0.35)))
    for room in rooms:
        if room.get("circle_px") and room.get("circle_m") and px_per_m:
            colour = _PASS if room.get("conforme") else _FAIL
            (cx, cy), r = room["circle_px"], room["circle_m"] / 2 * px_per_m
            _dashed_circle(draw, cx, cy, r, colour + (255,), max(2, round(unit * 0.35)))
    for door in body.get("doors") or []:
        (ax, ay), (bx, by) = door["doorway_px"]
        colour = _GREY if door.get("ok") is None else (_PASS if door["ok"] else _FAIL)
        draw.line([(ax, ay), (bx, by)], fill=colour + (255,), width=max(3, round(unit * 0.9)))
    for step in (body.get("walk") or {}).get("route", []):
        if step.get("event") in ("blocked_door", "cannot_turn"):
            x, y = step["point_px"]
            r = unit * 1.6
            draw.ellipse([x - r, y - r, x + r, y + r], fill=_FAIL + (255,), outline=(255, 255, 255, 255),
                         width=max(1, round(unit * 0.3)))

    out = Image.alpha_composite(base, overlay)
    text = ImageDraw.Draw(out)
    font = ImageFont.load_default(size=max(10, round(unit * 2.4)))
    for i, room in enumerate(rooms):
        x, y = _centre(room)
        text.text((x, y), str(i + 1), fill=_INK, font=font, anchor="mm",
                  stroke_width=max(2, round(unit * 0.4)), stroke_fill=(255, 255, 255))
    return out.convert("RGB")


def _dashed_circle(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, fill, width: int) -> None:
    box = [cx - r, cy - r, cx + r, cy + r]
    for start in range(0, 360, 12):
        draw.arc(box, start, start + 7, fill=fill, width=width)


def _centre(room: dict) -> tuple[float, float]:
    if room.get("circle_px"):
        return tuple(room["circle_px"])
    xs, ys = zip(*room["polygon_px"])
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _crop(image: Image.Image, room: dict) -> Image.Image:
    xs = [p[0] for p in room["polygon_px"]]
    ys = [p[1] for p in room["polygon_px"]]
    w, h = image.size
    return image.crop((max(0, int(min(xs)) - CROP_PAD_PX), max(0, int(min(ys)) - CROP_PAD_PX),
                       min(w, int(max(xs)) + CROP_PAD_PX), min(h, int(max(ys)) + CROP_PAD_PX)))


def _fit(image: Image.Image, max_w: float, max_h: float) -> RLImage:
    png = io.BytesIO()
    image.save(png, format="PNG", optimize=True)
    png.seek(0)
    scale = min(max_w / image.width, max_h / image.height)
    return RLImage(png, width=image.width * scale, height=image.height * scale)


# ── type and rules ───────────────────────────────────────────────────────────────────

def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("muted", parent=styles["Normal"], fontSize=8.5, textColor=GREY, leading=11))
    styles.add(ParagraphStyle("note", parent=styles["Normal"], fontSize=8.5, textColor=colors.Color(0.18, 0.35, 0.65),
                              leading=11, spaceBefore=3))
    styles.add(ParagraphStyle("eyebrow", parent=styles["Normal"], fontSize=8, textColor=GREY, leading=10,
                              fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle("cell", parent=styles["Normal"], fontSize=8.5, leading=10.5))
    styles.add(ParagraphStyle("banner", parent=styles["Normal"], fontSize=12, leading=15, fontName="Helvetica-Bold"))
    return styles


def _p(text: str, styles) -> Paragraph:
    return Paragraph(escape(text), styles["cell"])


def _banner(ok: bool, text: str, styles) -> Table:
    banner = Table([[Paragraph(escape(("PASSES — " if ok else "FAILS — ") + text), styles["banner"])]],
                   colWidths=[A4[0] - 2 * MARGIN])
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PASS_BG if ok else FAIL_BG),
        ("TEXTCOLOR", (0, 0), (-1, -1), PASS if ok else FAIL),
        ("LINEBEFORE", (0, 0), (0, -1), 3, PASS if ok else FAIL),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return banner


def _table_style() -> list:
    return [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.Color(0.98, 0.98, 0.99)]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]


def _colour_cell(style: list, col: int, row: int, ok: bool) -> None:
    style.append(("BACKGROUND", (col, row), (col, row), PASS_BG if ok else FAIL_BG))
    style.append(("TEXTCOLOR", (col, row), (col, row), PASS if ok else FAIL))


def _room_name(rooms: list[dict], i: int | None) -> str:
    if i is None or not 0 <= i < len(rooms):
        return "outside the rooms"
    return rooms[i].get("name") or f"Room {i + 1}"


def _m(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GREY)
    canvas.drawString(MARGIN, MARGIN * 0.6,
                      "ConformScope · a decision aid: it does not replace a certified accessibility audit")
    canvas.drawRightString(A4[0] - MARGIN, MARGIN * 0.6, f"Page {doc.page}")
    canvas.restoreState()
