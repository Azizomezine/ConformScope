"""The PDF report for a dossier: what the auditor hands over once every sheet is reviewed.

Ported from pmr-checker's `api/report.py`. A **report** is built from the stored readings
only -- the same rooms, doors, walk and explanations the check screen shows, corrections
and overrides included -- so it never measures again and never calls a model.

It reads from the verdict down:

- a cover: the dossier's verdict, its numbers at a glance, the rules scorecard (the same
  five rules the report pane scores), what blocks the wheelchair, and one line per sheet;
- then, for every sheet checked: its own scorecard, the sheet annotated (rooms in their
  verdict colours, turning circles, doorways, transfer and washbasin spaces, stops) with
  a drawn legend, the rooms table with each shortfall, the doors too narrow, the walk,
  Muse Spark's explanations as cards, and a grid of crops around every failing room.

A sheet never opened, or a plan annexe, is listed and not reported on. Layout is reportlab
platypus on two page templates (cover, body) with a running header and "Page x of y";
the annotated images are drawn with Pillow on the sheet's PNG.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Flowable, Frame, HRFlowable,
                                Image as RLImage, KeepTogether, NextPageTemplate, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)

MARGIN = 1.6 * cm
BAND_H = 2.4 * cm  # the ink band across the top of the cover
CROP_PAD_PX = 40  # around a failing room's outline, so the crop shows its walls
CROP_MIN_FRACTION = 1 / 7  # a crop spans at least this much of the sheet, so a WC is not a blur
REQUIRED_DIAMETER_M = 1.5
PAGE_W, PAGE_H = A4
WIDTH = PAGE_W - 2 * MARGIN

PASS = colors.Color(0.12, 0.55, 0.32)
PASS_BG = colors.Color(0.9, 0.97, 0.92)
FAIL = colors.Color(0.78, 0.22, 0.15)
FAIL_BG = colors.Color(1, 0.93, 0.92)
GREY = colors.Color(0.45, 0.5, 0.55)
GREY_BG = colors.Color(0.95, 0.96, 0.97)
INK = colors.Color(0.06, 0.11, 0.15)
COBALT = colors.Color(0.29, 0.51, 0.85)
COBALT_BG = colors.Color(0.93, 0.95, 0.99)
RULE = colors.Color(0.86, 0.88, 0.9)
PAPER = colors.Color(0.985, 0.987, 0.99)

# The same palette on the images, as RGB.
_PASS = (31, 157, 92)
_FAIL = (216, 64, 44)
_GREY = (138, 151, 163)
_COBALT = (75, 131, 216)
_INK = (16, 28, 39)

# The rules ConformScope checks, as web/lib/rules.ts lists them for the report pane.
RULES = [
    ("turning", "Turning circle", "Ø 1.50 m",
     "The largest free circle in each room, furniture placed, must reach Ø1.50 m.", "Arrêté du 24/12/2015"),
    ("doors", "Door width", "0.80 / 0.90 m",
     "Read from each door's swing arc: 0.80 m interior, 0.90 m for the entrance.", "Arrêté du 24/12/2015"),
    ("transfer", "Transfer space beside the toilet", "0.80 × 1.30 m",
     "A free space next to the toilet, where a wheelchair parks to move across.", "Arrêté du 24/12/2015"),
    ("washbasin", "Washbasin space", "0.80 × 1.30 m",
     "A free space in front of the washbasin, so a wheelchair can face it.", "Article to confirm"),
    ("walk", "Walk the home", "door → room",
     "A wheelchair rolls in from the entrance and stops at the first door too narrow.", "Built on the door rule"),
]

_KIND_LABEL = {"turning": "Turning circle", "door": "Door", "doors": "Door", "transfer": "Transfer space",
               "washbasin": "Washbasin space", "walk": "Walk"}


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
    doc = _Doc(buf, title)
    checked = [s for s in sheets if s.body and s.body.get("checked")]

    story: list = _cover(title, sheets, checked, today or date.today(), styles)
    story.append(NextPageTemplate("body"))
    for s in checked:
        story += [PageBreak(), _Section(s.sheet["name"])]
        story += _sheet_story(s, styles, WIDTH)

    doc.build(story, canvasmaker=_NumberedCanvas)
    return buf.getvalue()


# ── the pages ────────────────────────────────────────────────────────────────────────

class _Doc(BaseDocTemplate):
    """A cover with the ink band, then body pages with a running header."""

    def __init__(self, buf, title: str):
        super().__init__(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                         topMargin=MARGIN, bottomMargin=MARGIN,
                         title=f"ConformScope report: {title}", author="ConformScope",
                         subject="Wheelchair accessibility check")
        self.report_title = title
        footer_room = MARGIN + 0.4 * cm
        cover = Frame(MARGIN, footer_room, WIDTH, PAGE_H - BAND_H - 0.7 * cm - footer_room, id="cover",
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        body = Frame(MARGIN, footer_room, WIDTH, PAGE_H - MARGIN - 0.7 * cm - footer_room, id="body",
                     leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([
            PageTemplate("cover", [cover], onPage=_draw_band, onPageEnd=_draw_footer),
            PageTemplate("body", [body], onPageEnd=_draw_header_footer),
        ])


class _NumberedCanvas(rl_canvas.Canvas):
    """Holds every page back until the end, so each footer can say "Page x of y"."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._held: list[dict] = []

    def showPage(self):
        self._held.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._held)
        for state in self._held:
            self.__dict__.update(state)
            self.saveState()
            self.setFont("Helvetica", 7.5)
            self.setFillColor(GREY)
            self.drawRightString(PAGE_W - MARGIN, MARGIN * 0.6, f"Page {self._pageNumber} of {total}")
            self.restoreState()
            super().showPage()
        super().save()


class _Section(Flowable):
    """Names the sheet the pages from here on report on, for the running header."""

    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def wrap(self, *_):
        return 0, 0

    def draw(self):
        self.canv._report_section = self.name


def _draw_band(canvas, doc) -> None:
    canvas.saveState()
    top = PAGE_H - BAND_H
    canvas.setFillColor(INK)
    canvas.rect(0, top, PAGE_W, BAND_H, stroke=0, fill=1)
    canvas.setFillColor(COBALT)
    canvas.rect(0, top, PAGE_W, 0.12 * cm, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 13)
    canvas.drawString(MARGIN, top + BAND_H / 2 - 4, "CONFORMSCOPE", charSpace=2.2)
    canvas.setFillColor(colors.Color(0.72, 0.78, 0.84))
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(PAGE_W - MARGIN, top + BAND_H / 2 - 3, "Wheelchair accessibility report")
    canvas.restoreState()


def _draw_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, MARGIN * 0.6 + 10, PAGE_W - MARGIN, MARGIN * 0.6 + 10)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GREY)
    canvas.drawString(MARGIN, MARGIN * 0.6,
                      "ConformScope · a decision aid: it does not replace a certified accessibility audit")
    canvas.restoreState()


def _draw_header_footer(canvas, doc) -> None:
    canvas.saveState()
    y = PAGE_H - MARGIN + 4
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.setFillColor(INK)
    canvas.drawString(MARGIN, y, "CONFORMSCOPE")
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GREY)
    brand = canvas.stringWidth("CONFORMSCOPE", "Helvetica-Bold", 7.5) + 8
    canvas.drawString(MARGIN + brand, y, "· " + _clip(doc.report_title, 60))
    section = getattr(canvas, "_report_section", "")
    if section:
        canvas.drawRightString(PAGE_W - MARGIN, y, "Sheet: " + _clip(section, 50))
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, y - 5, PAGE_W - MARGIN, y - 5)
    canvas.restoreState()
    _draw_footer(canvas, doc)


# ── the cover ────────────────────────────────────────────────────────────────────────

def _cover(title: str, sheets: list[SheetReport], checked: list[SheetReport], today: date, styles) -> list:
    reportable = [s for s in sheets if not s.sheet.get("annexe")]
    story: list = [
        Paragraph("Accessibility report", styles["eyebrow"]),
        Paragraph(escape(title), styles["title"]),
        Paragraph(f"Generated on {today.isoformat()} from the reviewed readings, corrections and "
                  f"overrides included · {len(checked)} of {len(reportable)} sheets checked.",
                  styles["muted"]),
        Spacer(1, 0.45 * cm),
    ]
    if not checked:
        story.append(Paragraph("No sheet has been checked yet.", styles["h2"]))
        story += [Spacer(1, 0.4 * cm), *_heading("Sheets in the dossier", styles),
                  _dossier_table(sheets, styles, WIDTH)]
        return story

    scores = _sum_scores([_score_rules(s.body) for s in checked])
    measured = [sc for sc in scores if sc[0][0] != "walk"]
    checks = sum(total for _, _, total in measured)
    fails = sum(total - passed for _, passed, total in measured)
    ok = all(_sheet_passes(s.body) for s in checked)
    detail = (f"All {checks} checks pass on {_plural(len(checked), 'sheet')}." if ok else
              f"{fails} of {checks} checks fail across {_plural(len(checked), 'sheet')}. "
              "The most blocking issues are listed first.")
    story += [_banner(ok, "Every checked sheet passes" if ok else "Some checks fail: see the sheets below",
                      styles, detail), Spacer(1, 0.4 * cm)]

    rules_applied = sum(1 for _, _, total in scores if total > 0)
    walk = next(sc for sc in scores if sc[0][0] == "walk")
    story.append(_tiles([
        (str(checks), "checks run", None),
        (str(fails), "failing" if fails != 1 else "failing check", fails == 0),
        (f"{rules_applied}/{len(RULES)}", "rules applied", None),
        (f"{walk[1]}/{walk[2]}" if walk[2] else "—", "rooms the wheelchair reaches",
         None if not walk[2] else walk[1] == walk[2]),
    ], styles, WIDTH))

    blocking = _blocking(checked)
    if blocking:
        story += [Spacer(1, 0.5 * cm), *_heading("What blocks the wheelchair", styles)]
        for sheet_name, text in blocking[:8]:
            story.append(Paragraph(f"<font size='12' color='#{FAIL.hexval()[2:]}'>•</font>&nbsp;&nbsp;"
                                   f"<b>{escape(sheet_name)}</b> · {escape(text)}", styles["body"]))
        if len(blocking) > 8:
            story.append(Paragraph(f"…and {len(blocking) - 8} more in the sheets below.", styles["muted"]))

    story += [Spacer(1, 0.5 * cm), *_heading("Rules checked", styles), _rules_table(scores, styles, WIDTH),
              Spacer(1, 0.5 * cm), *_heading("Sheets in the dossier", styles),
              _dossier_table(sheets, styles, WIDTH)]
    return story


def _blocking(checked: list[SheetReport]) -> list[tuple[str, str]]:
    """Where the walk stops, sheet by sheet: one stop shuts out every room behind it."""
    out = []
    for s in checked:
        body = s.body
        rooms = body.get("rooms", [])
        walk = body.get("walk") or {}
        for stop in walk.get("stops", []):
            where = "At a door" if stop.get("kind") == "door" else _room_ref(rooms, stop.get("room"))
            behind = len(walk.get("unreachable", []))
            tail = f" — {behind} rooms not reached" if behind and stop.get("kind") == "door" else ""
            out.append((s.sheet["name"], f"{where}: {stop.get('reason', '')}{tail}"))
    return out


def _rules_table(scores, styles, width: float) -> Table:
    rows = [["", "Rule", "Requirement", "Result", "Source"]]
    style = _table_style()
    for i, ((rid, name, value, text, source), passed, total) in enumerate(scores, start=1):
        ok = None if total == 0 else passed == total
        result = "nothing to judge" if total == 0 else (
            f"{passed}/{total} rooms reached" if rid == "walk" else f"{passed}/{total} pass")
        rows.append([_Dot(_tone(ok)),
                     Paragraph(f"<b>{escape(name)}</b><br/><font size='7.5' color='#{GREY.hexval()[2:]}'>"
                               f"{escape(text)}</font>", styles["cell"]),
                     Paragraph(escape(value), styles["cellbold"]), result, Paragraph(escape(source), styles["cellmuted"])])
        if ok is not None:
            _colour_cell(style, 3, i, ok)
        else:
            style.append(("TEXTCOLOR", (3, i), (3, i), GREY))
    style += [("ALIGN", (0, 1), (0, -1), "CENTER"), ("VALIGN", (0, 1), (0, -1), "MIDDLE")]
    table = Table(rows, colWidths=[w * width for w in (0.05, 0.45, 0.15, 0.18, 0.17)], repeatRows=1)
    table.setStyle(TableStyle(style))
    return table


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


def _score_rules(body: dict) -> list[tuple[tuple, int, int]]:
    """How each rule did on one sheet, as scoreRules in web/lib/rules.ts: a rule with
    nothing to judge has total 0."""
    rooms = [r for r in body.get("rooms", []) if r.get("conforme") is not None]
    doors = [d for d in body.get("doors") or [] if d.get("ok") is not None]
    spaces = [f["space"] for f in body.get("fixtures") or [] if f.get("space")]
    walk = body.get("walk") or {}
    counts = {
        "turning": (sum(1 for r in rooms if r["conforme"]), len(rooms)),
        "doors": (sum(1 for d in doors if d["ok"]), len(doors)),
        "walk": (len(walk.get("reached", [])), len(body.get("rooms", []))) if walk.get("route") else (0, 0),
    }
    for kind in ("transfer", "washbasin"):
        of = [s for s in spaces if s.get("kind") == kind]
        counts[kind] = (sum(1 for s in of if s.get("fits")), len(of))
    return [(rule, *counts[rule[0]]) for rule in RULES]


def _sum_scores(per_sheet: list[list]) -> list[tuple[tuple, int, int]]:
    return [(rule, sum(sheet[i][1] for sheet in per_sheet), sum(sheet[i][2] for sheet in per_sheet))
            for i, rule in enumerate(RULES)]


def _dossier_table(sheets: list[SheetReport], styles, width: float) -> Table:
    rows = [["Sheet", "Status", "Turning circle", "Doors", "WC", "Walk"]]
    style = _table_style()
    for i, s in enumerate(sheets, start=1):
        body = s.body
        if s.sheet.get("annexe"):
            rows.append([_p(s.sheet["name"], styles), "Plan annexe, not checked", "", "", "", ""])
            style += [("SPAN", (1, i), (-1, i)), ("TEXTCOLOR", (1, i), (-1, i), GREY)]
            continue
        if not body or not body.get("checked"):
            rows.append([_p(s.sheet["name"], styles), "Not opened yet", "", "", "", ""])
            style += [("SPAN", (1, i), (-1, i)), ("TEXTCOLOR", (1, i), (-1, i), GREY)]
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
        if judged:
            _tone_text(style, 2, i, passing == judged)
        if _doors_ok(body) is not None:
            _tone_text(style, 3, i, not narrow)
        if wc is not None:
            _tone_text(style, 4, i, wc)
        if walk.get("route"):
            _tone_text(style, 5, i, reached == total)
    table = Table(rows, colWidths=[w * width for w in (0.24, 0.12, 0.17, 0.16, 0.13, 0.18)], repeatRows=1)
    table.setStyle(TableStyle(style))
    return table


# ── one sheet ────────────────────────────────────────────────────────────────────────

def _sheet_story(s: SheetReport, styles, width: float) -> list:
    body = s.body or {}
    rooms = body.get("rooms", [])
    passing, judged = _counts(body)
    scale = body.get("scale") or "no written scale"
    source = body.get("scale_source")
    story: list = [
        Paragraph("Sheet", styles["eyebrow"]),
        Paragraph(escape(s.sheet["name"]), styles["h1"]),
        Paragraph(escape(f"Scale {scale}" + (f", {source.replace('_', ' ')}" if source else "")
                         + f" · {len(rooms)} rooms measured"), styles["muted"]),
        Spacer(1, 0.3 * cm),
        _banner(_sheet_passes(body),
                f"{passing}/{judged} rooms fit the Ø{REQUIRED_DIAMETER_M:.2f} m turning circle", styles),
        Spacer(1, 0.3 * cm),
        _tiles([(f"{p}/{t}" if t else "—", name, None if not t else p == t)
                for (_, name, *_), p, t in _score_rules(body)], styles, width, small=True),
        Spacer(1, 0.35 * cm),
    ]

    annotated = annotate(s.image, body) if s.image is not None else None
    if annotated is not None:
        story += [_framed(_fit(annotated, width - 8, 14 * cm), width), Spacer(1, 0.15 * cm),
                  _Legend(width)]

    warnings = body.get("warnings", [])
    if warnings:
        story += [Spacer(1, 0.25 * cm), _note_box(warnings, styles, width)]

    story += [Spacer(1, 0.35 * cm), *_heading("Rooms", styles), _rooms_table(rooms, styles, width)]

    doors = body.get("doors") or []
    narrow = [d for d in doors if d.get("ok") is False]
    if _doors_ok(body) is not None:
        judged_doors = [d for d in doors if d.get("ok") is not None]
        part = [Spacer(1, 0.4 * cm), *_heading("Doors", styles)]
        if not narrow:
            part.append(Paragraph(f"All {len(judged_doors)} doors checked are wide enough.", styles["body"]))
        else:
            part += [Paragraph(f"{len(narrow)} of {len(judged_doors)} doors checked are too narrow.",
                               styles["muted"]), Spacer(1, 0.1 * cm),
                     _doors_table(narrow, rooms, styles, width)]
        story.append(KeepTogether(part))

    spaces = [f for f in body.get("fixtures") or [] if f.get("space")]
    if spaces or body.get("accessible_wc") is not None:
        part = [Spacer(1, 0.4 * cm), *_heading("Accessible WC and washbasin", styles)]
        if body.get("accessible_wc") is not None:
            part.append(Paragraph("A toilet has a 0.80 × 1.30 m transfer space beside it." if body["accessible_wc"]
                                  else "No toilet has a 0.80 × 1.30 m transfer space beside it.", styles["body"]))
        if spaces:
            part += [Spacer(1, 0.15 * cm), _spaces_table(spaces, rooms, styles, width)]
        story.append(KeepTogether(part))

    walk = body.get("walk") or {}
    if walk.get("route"):
        part = [Spacer(1, 0.4 * cm), *_heading("Walk the plan", styles),
                Paragraph(escape(walk.get("verdict", "")), styles["bodybold"])]
        for stop in walk.get("stops", []):
            where = "At a door" if stop.get("kind") == "door" else _room_ref(rooms, stop.get("room"))
            part.append(Paragraph(f"<font size='12' color='#{FAIL.hexval()[2:]}'>•</font>&nbsp;&nbsp;"
                                  + escape(f"{where}: {stop.get('reason', '')}"), styles["body"]))
        if walk.get("unreachable"):
            names = ", ".join(_room_ref(rooms, u["room"]) for u in walk["unreachable"])
            part.append(Paragraph(escape(f"Not reached ({len(walk['unreachable'])}): {names}"), styles["muted"]))
        story.append(KeepTogether(part))

    explain = body.get("explain") or {}
    if explain.get("failures"):
        story += [CondPageBreak(6 * cm), Spacer(1, 0.4 * cm), *_heading("Why it fails, and how to fix it", styles)]
        if explain.get("explained_by"):
            story.append(Paragraph(escape(f"Explained by {explain['explained_by']}"
                                          + (f", verified by {explain['verified_by']}" if explain.get("verified_by") else "")),
                                   styles["muted"]))
            story.append(Spacer(1, 0.15 * cm))
        story.append(_failure_grid(explain["failures"], styles, width))

    failing = [(i, r) for i, r in enumerate(rooms) if r.get("conforme") is False and r.get("polygon_px")]
    if failing and annotated is not None:
        story += [CondPageBreak(9 * cm), Spacer(1, 0.4 * cm), *_heading("Rooms that fail, on the plan", styles),
                  _crop_grid(annotated, rooms, failing, styles, width)]
    return story


def _rooms_table(rooms: list[dict], styles, width: float):
    if not rooms:
        return Paragraph("No rooms were measured on this sheet.", styles["muted"])
    rows = [["No.", "Room", "Type", "Area", "Free Ø", "Short by", "Verdict"]]
    style = _table_style()
    for i, room in enumerate(rooms, start=1):
        ok = room.get("conforme")
        free = room.get("max_diameter_m")
        short = (f"{round((REQUIRED_DIAMETER_M - free) * 100)} cm"
                 if ok is False and free is not None and free < REQUIRED_DIAMETER_M else "")
        rows.append([str(i), _p(_room_name(rooms, i - 1), styles),
                     (room.get("room_type") or "").replace("_", " ").capitalize(),
                     f"{room['area_m2']:.1f} m²" if room.get("area_m2") is not None else "—",
                     f"{_m(free)} m" if free is not None else "—", short,
                     "Not checked" if ok is None else ("Pass" if ok else "Fails")])
        if ok is None:
            style.append(("TEXTCOLOR", (6, i), (6, i), GREY))
        else:
            _colour_cell(style, 6, i, ok)
        if ok is False:
            style += [("TEXTCOLOR", (5, i), (5, i), FAIL), ("FONTNAME", (0, i), (0, i), "Helvetica-Bold")]
    style += [("ALIGN", (3, 0), (5, -1), "RIGHT"), ("ALIGN", (0, 0), (0, -1), "CENTER")]
    table = Table(rows, colWidths=[w * width for w in (0.07, 0.31, 0.15, 0.11, 0.11, 0.11, 0.14)], repeatRows=1)
    table.setStyle(TableStyle(style))
    return table


def _doors_table(doors: list[dict], rooms: list[dict], styles, width: float) -> Table:
    rows = [["Between", "Role", "Width", "Needs", "Verdict"]]
    style = _table_style()
    for i, door in enumerate(doors, start=1):
        sides = " – ".join("outside" if r is None else _room_ref(rooms, r) for r in door.get("rooms", []))
        rows.append([_p(sides, styles), (door.get("role") or "").capitalize(), f"{door['width_m']:.2f} m",
                     f"{door['required_m']:.2f} m" if door.get("required_m") is not None else "—", "Too narrow"])
        _colour_cell(style, 4, i, False)
    style.append(("ALIGN", (2, 0), (3, -1), "RIGHT"))
    table = Table(rows, colWidths=[w * width for w in (0.45, 0.14, 0.13, 0.13, 0.15)], repeatRows=1)
    table.setStyle(TableStyle(style))
    return table


def _spaces_table(fixtures: list[dict], rooms: list[dict], styles, width: float) -> Table:
    rows = [["Fixture", "Room", "Space needed", "Verdict"]]
    style = _table_style()
    # The spaces missing first: they are what the auditor acts on.
    fixtures = sorted(fixtures, key=lambda f: (bool(f["space"].get("fits")), f.get("kind") or ""))
    for i, fixture in enumerate(fixtures, start=1):
        space = fixture["space"]
        kind = "Transfer beside it" if space.get("kind") == "transfer" else "In front of it"
        verdict = space.get("verdict") or ("Space found" if space.get("fits") else "No space")
        if space.get("to_confirm") and "confirm" not in verdict:
            verdict += " (to confirm)"
        rows.append([(fixture.get("kind") or "").capitalize(), _p(_room_ref(rooms, fixture.get("room")), styles),
                     f"{kind}, 0.80 × 1.30 m", _p(verdict, styles)])
        _colour_cell(style, 3, i, bool(space.get("fits")))
    table = Table(rows, colWidths=[w * width for w in (0.16, 0.30, 0.27, 0.27)], repeatRows=1)
    table.setStyle(TableStyle(style))
    return table


def _failure_grid(failures: list[dict], styles, width: float) -> Table:
    """Each failure as a card, two to a row, so a long list reads like a checklist."""
    gap = 0.35 * cm
    col = (width - gap) / 2
    cards = [_failure_card(f, styles, col) for f in failures]
    if len(cards) % 2:
        cards.append("")
    rows = [[cards[i], "", cards[i + 1]] for i in range(0, len(cards), 2)]
    table = Table(rows, colWidths=[col, gap, col])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), gap)]))
    return table


def _failure_card(failure: dict, styles, width: float) -> Table:
    verify = failure.get("verify") or {}
    if verify.get("status") == "verified":
        pct = round(100 * verify.get("confidence", 0))
        second = (f"Doubtful: the verifier {'is unsure' if verify.get('agree') else 'disagrees'} ({pct}%). "
                  f"{verify.get('note', '')}" if verify.get("doubtful") else f"Verified ({pct}%).")
        tone = FAIL if verify.get("doubtful") else PASS
    else:
        second, tone = "Not verified.", GREY
    if failure.get("source") == "template":
        second += " Written from the measurements."
    kind = _KIND_LABEL.get(failure.get("kind") or "", (failure.get("kind") or "").capitalize())
    measured, required = failure.get("measured_m"), failure.get("required_m")
    numbers = (f" · {measured:.2f} m, needs {required:.2f} m"
               if isinstance(measured, (int, float)) and isinstance(required, (int, float)) else "")
    content = [
        Paragraph(escape(kind.upper() + numbers), styles["tag"]),
        Paragraph(f"<b>{escape(failure.get('subject', ''))}</b>", styles["body"]),
        Paragraph(escape(failure.get("reason", "")), styles["small"]),
        Spacer(1, 3),
        Table([[Paragraph(f"<b>Fix</b>&nbsp;&nbsp;{escape(failure.get('fix', ''))}", styles["fix"])]],
              colWidths=[width - 18],
              style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), COBALT_BG),
                                ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                                ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)])),
        Spacer(1, 3),
        Paragraph(f"<font size='11' color='#{tone.hexval()[2:]}'>•</font>&nbsp;{escape(second)}", styles["muted"]),
    ]
    card = Table([[content]], colWidths=[width])
    card.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, RULE), ("LINEBEFORE", (0, 0), (0, -1), 2.5, FAIL),
                              ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                              ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                              ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return card


def _crop_grid(annotated: Image.Image, rooms: list[dict], failing: list[tuple[int, dict]], styles,
               width: float) -> Table:
    gap = 0.35 * cm
    col = (width - gap) / 2
    box_h = 5.6 * cm
    cells = []
    for i, room in failing:
        free = room.get("max_diameter_m")
        short = (f" · short by {round((REQUIRED_DIAMETER_M - free) * 100)} cm"
                 if free is not None and free < REQUIRED_DIAMETER_M else "")
        caption = (f"{i + 1}. {_room_name(rooms, i)} — fails: free Ø"
                   f"{_m(free)} m, needs Ø{REQUIRED_DIAMETER_M:.2f} m")
        image = _fit(_crop(annotated, room), col - 12, box_h)
        cell = Table([[Paragraph(escape(caption), styles["cellbold"])],
                      [Paragraph(escape((room.get("room_type") or "room").replace("_", " ").capitalize()
                                        + (f" · {room['area_m2']:.1f} m²" if room.get("area_m2") is not None else "")
                                        + short), styles["cellmuted"])],
                      [image]],
                     colWidths=[col], rowHeights=[None, None, box_h + 8])
        cell.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, RULE),
                                  ("BACKGROUND", (0, 2), (0, 2), PAPER),
                                  ("ALIGN", (0, 2), (0, 2), "CENTER"), ("VALIGN", (0, 2), (0, 2), "MIDDLE"),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                                  ("TOPPADDING", (0, 0), (0, 0), 6), ("BOTTOMPADDING", (0, 1), (0, 1), 5),
                                  ("TOPPADDING", (0, 1), (0, 1), 1)]))
        cells.append(cell)
    if len(cells) % 2:
        cells.append("")
    rows = [[cells[i], "", cells[i + 1]] for i in range(0, len(cells), 2)]
    table = Table(rows, colWidths=[col, gap, col])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), gap)]))
    return table


# ── the images ───────────────────────────────────────────────────────────────────────

def annotate(image: Image.Image, body: dict) -> Image.Image:
    """The sheet with its verdicts drawn on it, as the check screen draws them."""
    base = image.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    unit = max(base.size) / 200  # one mark size whatever the sheet's resolution
    rooms = body.get("rooms", [])
    px_per_m = body.get("px_per_m")
    line = max(2, round(unit * 0.35))

    for room in rooms:
        colour = _GREY if room.get("conforme") is None else (_PASS if room["conforme"] else _FAIL)
        polygon = [tuple(p) for p in room.get("polygon_px", [])]
        if len(polygon) >= 3:
            draw.polygon(polygon, fill=colour + (34,), outline=colour + (255,), width=line)
    for fixture in body.get("fixtures") or []:
        space = fixture.get("space") or {}
        polygon = [tuple(p) for p in space.get("polygon_px") or []]
        if len(polygon) >= 3:
            colour = _PASS if space.get("fits") else _FAIL
            draw.polygon(polygon, fill=colour + (46,))
            _dashed_polyline(draw, polygon + polygon[:1], colour + (255,), line, dash=unit * 1.1)
    for room in rooms:
        if room.get("circle_px") and room.get("circle_m") and px_per_m:
            colour = _PASS if room.get("conforme") else _FAIL
            (cx, cy), r = room["circle_px"], room["circle_m"] / 2 * px_per_m
            _dashed_circle(draw, cx, cy, r, colour + (255,), line)
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
        if not room.get("circle_px") and not room.get("polygon_px"):
            continue
        x, y = _centre(room)
        text.text((x, y), str(i + 1), fill=_INK, font=font, anchor="mm",
                  stroke_width=max(2, round(unit * 0.4)), stroke_fill=(255, 255, 255))
    return out.convert("RGB")


def _dashed_circle(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, fill, width: int) -> None:
    box = [cx - r, cy - r, cx + r, cy + r]
    for start in range(0, 360, 12):
        draw.arc(box, start, start + 7, fill=fill, width=width)


def _dashed_polyline(draw: ImageDraw.ImageDraw, points: list, fill, width: int, dash: float) -> None:
    dash = max(dash, 2.0)
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        length = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
        if not length:
            continue
        steps = int(length // dash)
        for k in range(0, steps + 1, 2):
            t0, t1 = k * dash / length, min(1.0, (k + 1) * dash / length)
            draw.line([(ax + (bx - ax) * t0, ay + (by - ay) * t0), (ax + (bx - ax) * t1, ay + (by - ay) * t1)],
                      fill=fill, width=width)


def _centre(room: dict) -> tuple[float, float]:
    if room.get("circle_px"):
        return tuple(room["circle_px"])
    xs, ys = zip(*room["polygon_px"])
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _crop(image: Image.Image, room: dict) -> Image.Image:
    """Around the room's outline, widened to a minimum so a small room keeps its context."""
    xs = [p[0] for p in room["polygon_px"]]
    ys = [p[1] for p in room["polygon_px"]]
    w, h = image.size
    least = max(w, h) * CROP_MIN_FRACTION
    left, right = min(xs) - CROP_PAD_PX, max(xs) + CROP_PAD_PX
    top, bottom = min(ys) - CROP_PAD_PX, max(ys) + CROP_PAD_PX
    if right - left < least:
        grow = (least - (right - left)) / 2
        left, right = left - grow, right + grow
    if bottom - top < least * 0.7:
        grow = (least * 0.7 - (bottom - top)) / 2
        top, bottom = top - grow, bottom + grow
    return image.crop((max(0, int(left)), max(0, int(top)), min(w, int(right)), min(h, int(bottom))))


def _fit(image: Image.Image, max_w: float, max_h: float) -> RLImage:
    png = io.BytesIO()
    image.save(png, format="PNG", optimize=True)
    png.seek(0)
    scale = min(max_w / image.width, max_h / image.height)
    return RLImage(png, width=image.width * scale, height=image.height * scale)


def _framed(image: RLImage, width: float) -> Table:
    frame = Table([[image]], colWidths=[width])
    frame.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, RULE), ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                               ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return frame


class _Legend(Flowable):
    """What the marks on the annotated sheet mean, drawn with the same marks."""

    ITEMS = [("fill", PASS, "Room passes"), ("fill", FAIL, "Room fails"), ("fill", GREY, "Not checked"),
             ("ring", INK, "Largest free turning circle"), ("line", INK, "Doorway, in its verdict colour"),
             ("box", PASS, "Transfer / washbasin space"), ("dot", FAIL, "Where the wheelchair stops")]
    COLS = 4
    ROW_H = 12

    def __init__(self, width: float):
        super().__init__()
        self.width = width

    def wrap(self, *_):
        rows = -(-len(self.ITEMS) // self.COLS)
        return self.width, rows * self.ROW_H

    def draw(self):
        c = self.canv
        col_w = self.width / self.COLS
        rows = -(-len(self.ITEMS) // self.COLS)
        for n, (mark, colour, label) in enumerate(self.ITEMS):
            x = (n % self.COLS) * col_w
            y = (rows - 1 - n // self.COLS) * self.ROW_H + 3
            _mark(c, mark, colour, x + 5, y + 3)
            c.setFont("Helvetica", 7.5)
            c.setFillColor(GREY)
            c.drawString(x + 14, y, label)


def _mark(c, mark: str, colour, x: float, y: float) -> None:
    """One legend mark centred on (x, y)."""
    c.saveState()
    c.setStrokeColor(colour)
    c.setFillColor(colour)
    if mark == "fill":
        c.setFillColor(colors.Color(colour.red, colour.green, colour.blue, alpha=0.2))
        c.setLineWidth(1)
        c.rect(x - 4, y - 3.5, 8, 7, stroke=1, fill=1)
    elif mark == "ring":
        c.setDash(1.6, 1.2)
        c.setLineWidth(1)
        c.circle(x, y, 3.6, stroke=1, fill=0)
    elif mark == "line":
        c.setLineWidth(2.4)
        c.setStrokeColor(PASS)
        c.line(x - 5, y, x - 0.5, y)
        c.setStrokeColor(FAIL)
        c.line(x + 0.5, y, x + 5, y)
    elif mark == "box":
        c.setDash(1.6, 1.2)
        c.setLineWidth(1)
        c.rect(x - 4, y - 3.5, 8, 7, stroke=1, fill=0)
    elif mark == "dot":
        c.setStrokeColor(colors.white)
        c.circle(x, y, 3.2, stroke=1, fill=1)
    c.restoreState()


class _Dot(Flowable):
    """A verdict dot for a table cell."""

    def __init__(self, colour, size: float = 7):
        super().__init__()
        self.colour, self.size = colour, size

    def wrap(self, *_):
        return self.size, self.size

    def draw(self):
        self.canv.setFillColor(self.colour)
        self.canv.circle(self.size / 2, self.size / 2, self.size / 2, stroke=0, fill=1)


# ── type and rules ───────────────────────────────────────────────────────────────────

def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=13, textColor=INK)
    s = {"body": base}

    def add(name, **kw):
        s[name] = ParagraphStyle(name, parent=base, **kw)

    add("title", fontName="Helvetica-Bold", fontSize=24, leading=29, spaceAfter=4)
    add("h1", fontName="Helvetica-Bold", fontSize=19, leading=23, spaceAfter=2)
    add("h2", fontName="Helvetica-Bold", fontSize=12, leading=15)
    add("bodybold", fontName="Helvetica-Bold")
    add("small", fontSize=8.5, leading=11.5)
    add("muted", fontSize=8.5, leading=11.5, textColor=GREY)
    add("eyebrow", fontName="Helvetica-Bold", fontSize=7.5, leading=10, textColor=COBALT)
    add("tag", fontName="Helvetica-Bold", fontSize=6.8, leading=9, textColor=FAIL)
    add("fix", fontSize=8.5, leading=11.5, textColor=colors.Color(0.12, 0.27, 0.55))
    add("cell", fontSize=8.5, leading=10.5)
    add("cellbold", fontName="Helvetica-Bold", fontSize=8.5, leading=10.5)
    add("cellmuted", fontSize=7.8, leading=10, textColor=GREY)
    add("mono", fontName="Courier", fontSize=8.5, leading=10.5)
    add("banner", fontName="Helvetica-Bold", fontSize=12.5, leading=15.5)
    add("bannerdetail", fontSize=9, leading=12)
    add("tilevalue", fontName="Helvetica-Bold", fontSize=20, leading=23)
    add("tilevaluesmall", fontName="Helvetica-Bold", fontSize=14, leading=17)
    add("tilelabel", fontSize=7.5, leading=9.5, textColor=GREY)
    add("note", fontSize=8.5, leading=11.5, textColor=colors.Color(0.12, 0.27, 0.55))
    return s


def _heading(text: str, styles) -> list:
    return [Paragraph(escape(text), styles["h2"]), Spacer(1, 2),
            HRFlowable(width="100%", thickness=0.6, color=RULE, spaceBefore=0, spaceAfter=6)]


def _p(text: str, styles) -> Paragraph:
    return Paragraph(escape(text), styles["cell"])


def _banner(ok: bool, text: str, styles, detail: str | None = None) -> Table:
    tone = PASS if ok else FAIL
    head = ParagraphStyle("banner-tone", parent=styles["banner"], textColor=tone)
    sub = ParagraphStyle("bannerdetail-tone", parent=styles["bannerdetail"], textColor=tone)
    content = [Paragraph(escape(("PASSES — " if ok else "FAILS — ") + text), head)]
    if detail:
        content.append(Paragraph(escape(detail), sub))
    banner = Table([[content]], colWidths=[WIDTH])
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PASS_BG if ok else FAIL_BG),
        ("TEXTCOLOR", (0, 0), (-1, -1), tone),
        ("LINEBEFORE", (0, 0), (0, -1), 4, tone),
        ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
    ]))
    return banner


def _tiles(items: list[tuple[str, str, bool | None]], styles, width: float, small: bool = False) -> Table:
    """Numbers at a glance, one tile each, with a top rule in its verdict colour."""
    gap = 0.25 * cm
    n = len(items)
    tile_w = (width - gap * (n - 1)) / n
    value_style = styles["tilevaluesmall" if small else "tilevalue"]
    cells, widths, style = [], [], [("VALIGN", (0, 0), (-1, -1), "TOP"),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                                     ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]
    for k, (value, label, ok) in enumerate(items):
        col = k * 2
        tone = _tone(ok)
        cells.append([Paragraph(escape(value), ParagraphStyle(f"tv{k}", parent=value_style,
                                                             textColor=INK if ok is None else tone)),
                      Paragraph(escape(label), styles["tilelabel"])])
        widths.append(tile_w)
        style += [("BACKGROUND", (col, 0), (col, 0), PAPER), ("BOX", (col, 0), (col, 0), 0.5, RULE),
                  ("LINEABOVE", (col, 0), (col, 0), 2, COBALT if ok is None else tone)]
        if k < n - 1:
            cells.append("")
            widths.append(gap)
            style += [("LEFTPADDING", (col + 1, 0), (col + 1, 0), 0), ("RIGHTPADDING", (col + 1, 0), (col + 1, 0), 0)]
    table = Table([cells], colWidths=widths)
    table.setStyle(TableStyle(style))
    return table


def _note_box(warnings: list[str], styles, width: float) -> Table:
    content = [Paragraph(f"<b>Note</b>&nbsp;&nbsp;{escape(w)}", styles["note"]) for w in warnings]
    box = Table([[content]], colWidths=[width])
    box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), COBALT_BG),
                             ("LINEBEFORE", (0, 0), (0, -1), 2.5, COBALT),
                             ("LEFTPADDING", (0, 0), (-1, -1), 9),
                             ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return box


def _table_style() -> list:
    return [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("TEXTCOLOR", (0, 1), (-1, -1), INK),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ("BOX", (0, 0), (-1, -1), 0.4, RULE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PAPER]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]


def _tone(ok: bool | None):
    return GREY if ok is None else (PASS if ok else FAIL)


def _colour_cell(style: list, col: int, row: int, ok: bool) -> None:
    style.append(("BACKGROUND", (col, row), (col, row), PASS_BG if ok else FAIL_BG))
    style.append(("TEXTCOLOR", (col, row), (col, row), PASS if ok else FAIL))
    style.append(("FONTNAME", (col, row), (col, row), "Helvetica-Bold"))


def _tone_text(style: list, col: int, row: int, ok: bool) -> None:
    style.append(("TEXTCOLOR", (col, row), (col, row), PASS if ok else FAIL))


def _room_name(rooms: list[dict], i: int | None) -> str:
    if i is None or not 0 <= i < len(rooms):
        return "outside the rooms"
    return rooms[i].get("name") or f"Room {i + 1}"


def _room_ref(rooms: list[dict], i: int | None) -> str:
    """A room as the plan numbers it, so two bedrooms are told apart: "Bedroom (3)"."""
    if i is None or not 0 <= i < len(rooms):
        return "outside the rooms"
    name = rooms[i].get("name")
    return f"{name} ({i + 1})" if name else f"Room {i + 1}"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _clip(text: str, n: int) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


def _m(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"
