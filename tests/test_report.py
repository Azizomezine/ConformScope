import json

import pymupdf

from test_api import _open, _png_upload, _sheet_with_a_narrow_door, make_api  # noqa: F401 -- fixture

from conformscope.report import SheetReport, annotate, build


def _text(pdf: bytes) -> str:
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc)


def test_the_report_is_a_pdf_of_the_sheets_checked(make_api, tmp_path):
    api = make_api()
    plan_id, stored = _sheet_with_a_narrow_door(api, tmp_path)
    body = json.loads(stored.read_text(encoding="utf-8"))
    body["rooms"][1].update(conforme=False, max_diameter_m=1.21, area_m2=6.0)
    stored.write_text(json.dumps(body), encoding="utf-8")

    response = api.get(f"/plans/{plan_id}/report.pdf", params={"name": "Flat 2.pdf"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "conformscope-report-Flat-2.pdf" in response.headers["content-disposition"]
    text = _text(response.content)
    assert "Flat 2.pdf" in text and "FAILS" in text
    assert "Hall" in text and "Bedroom" in text
    assert "Too narrow" in text and "0.70 m" in text  # the narrow door, with its width
    assert "1 too narrow" in text  # and in the dossier at a glance
    assert "Rooms that fail, on the plan" in text  # a crop of the failing bedroom


def test_a_report_before_any_sheet_is_checked_is_a_409(make_api):
    api = make_api()
    plan_id = api.post("/plans", files=_png_upload()).json()["id"]

    assert api.get(f"/plans/{plan_id}/report.pdf").status_code == 409


def test_a_report_never_measures_again_nor_asks_a_model(make_api, tmp_path):
    api = make_api()
    plan_id, stored = _sheet_with_a_narrow_door(api, tmp_path)
    kept = stored.read_text(encoding="utf-8")
    broken = make_api(error=RuntimeError("no model now"))

    assert broken.get(f"/plans/{plan_id}/report.pdf").status_code == 200
    assert stored.read_text(encoding="utf-8") == kept


def test_an_unknown_plan_has_no_report(make_api):
    assert make_api().get("/plans/" + "0" * 32 + "/report.pdf").status_code == 404


def test_sheets_not_opened_and_annexes_are_listed_not_reported():
    checked = {"checked": True, "rooms": [], "doors": [], "doors_ok": None, "walk": None, "warnings": []}
    pdf = build("Building", [
        SheetReport({"page": 0, "name": "Level 1", "annexe": False}, checked, None),
        SheetReport({"page": 1, "name": "Level 2", "annexe": False}, None, None),
        SheetReport({"page": 2, "name": "Site plan", "annexe": True}, None, None),
    ])

    text = _text(pdf)
    assert "Not opened yet" in text and "Plan annexe, not checked" in text
    assert "Level 1" in text


def test_annotating_draws_on_a_copy_of_the_sheet():
    from PIL import Image
    sheet = Image.new("RGB", (400, 200), "white")
    body = {"px_per_m": 50, "rooms": [{"conforme": False, "circle_px": [100, 100], "circle_m": 1.2,
                                       "polygon_px": [[50, 50], [150, 50], [150, 150], [50, 150]]}],
            "doors": [{"doorway_px": [[150, 80], [150, 120]], "ok": True}], "walk": None}

    out = annotate(sheet, body)

    assert out.size == sheet.size
    assert sheet.getpixel((100, 60)) == (255, 255, 255)  # the sheet itself is untouched
    assert out.getpixel((100, 60)) != (255, 255, 255)  # the failing room is tinted
