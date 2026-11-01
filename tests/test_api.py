import io
from types import SimpleNamespace

import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from conformscope.api import create_app
from conformscope.client import MissingKeyError
from test_labels import RECORDED
from test_rooms import SAMPLE


def _model_client(reply=RECORDED, error=None, calls=None):
    def create(**kwargs):
        if calls is not None:
            calls.append(kwargs["response_format"]["json_schema"]["name"])
        if error:
            raise error
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=reply))])

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


@pytest.fixture
def make_api(tmp_path):
    def make(**kwargs):
        return TestClient(create_app(data_dir=tmp_path, model_client=lambda: _model_client(**kwargs)))
    return make


def _png_upload(size=(1754, 1240)):
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="PNG")
    return {"file": ("plan.png", buffer.getvalue(), "image/png")}


def _open(api, files, page=0):
    """Upload a dossier and open one of its sheets."""
    plan_id = api.post("/plans", files=files).json()["id"]
    return plan_id, api.get(f"/plans/{plan_id}/sheets/{page}")


def test_upload_returns_the_rooms_muse_spark_read(make_api):
    _, response = _open(make_api(), _png_upload())

    assert response.status_code == 200
    body = response.json()
    assert (body["width"], body["height"]) == (1754, 1240)
    assert body["scale"] == "1:100"
    assert len(body["labels"]) == 8
    assert body["labels"][0] == {"name": "Bedroom", "room_type": "bedroom",
                                 "x": 203, "y": 213, "area_m2": 15.31}


def test_uploaded_plan_can_be_fetched_again_with_its_image(make_api):
    api = make_api()
    plan_id, first = _open(api, _png_upload())

    again = api.get(f"/plans/{plan_id}/sheets/0")
    image = api.get(f"/plans/{plan_id}/sheets/0/image")

    assert again.status_code == 200
    assert again.json() == first.json()
    assert len(again.json()["labels"]) == 8
    assert image.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(image.content)).size == (1754, 1240)


def test_a_bad_model_reply_is_a_502_with_a_reason(make_api):
    _, response = _open(make_api(reply="Sorry, I can't read this plan."), _png_upload())

    assert response.status_code == 502
    assert "JSON" in response.json()["detail"]


def test_a_failed_model_call_is_a_502_with_a_reason(make_api):
    _, response = _open(make_api(error=RuntimeError("rate limited")), _png_upload())

    assert response.status_code == 502
    assert "rate limited" in response.json()["detail"]


def test_an_unsupported_file_is_a_400(make_api):
    response = make_api().post("/plans", files={"file": ("plan.docx", b"nope", "application/octet-stream")})

    assert response.status_code == 400


def test_an_unknown_plan_is_a_404(make_api):
    api = make_api()

    assert api.get("/plans/does-not-exist").status_code == 404
    assert api.get("/plans/..%2F..%2Fetc/sheets/0/image").status_code == 404
    plan_id = api.post("/plans", files=_png_upload()).json()["id"]
    assert api.get(f"/plans/{plan_id}/sheets/1").status_code == 404


def test_a_missing_key_is_a_503_that_says_so(tmp_path):
    def no_key():
        raise MissingKeyError("MODEL_API_KEY is not set.")

    api = TestClient(create_app(data_dir=tmp_path, model_client=no_key))

    plan_id, response = _open(api, _png_upload())

    assert response.status_code == 503
    assert "MODEL_API_KEY" in response.json()["detail"]
    assert not (tmp_path / plan_id / "sheets" / "0" / "reading.json").exists()


def test_a_picture_with_no_sam_answer_still_returns_its_labels_with_a_warning(make_api):
    # The fake client has no SAM endpoint, so segmenting fails; the upload must not.
    body = _open(make_api(), _png_upload())[1].json()

    assert body["kind"] == "picture"
    assert body["rooms"] == []
    assert any("SAM 3.1" in w for w in body["warnings"])
    assert body["fixtures"] == [] and body["accessible_wc"] is None


@pytest.mark.skipif(not SAMPLE.exists(), reason="private sample plan not present")
def test_a_vector_plan_comes_back_with_measured_rooms(make_api):
    upload = {"file": ("plan.pdf", SAMPLE.read_bytes(), "application/pdf")}

    body = _open(make_api(), upload)[1].json()

    assert body["kind"] == "vector"
    assert body["scale_source"] == "measured"
    bedroom = next(r for r in body["rooms"] if r["written_area_m2"] == 16.14)
    assert bedroom["area_m2"] == pytest.approx(16.14, rel=0.05)
    assert {"name", "room_type", "type_source", "polygon_px", "polygon_m", "circle_m",
            "circle_px", "warnings", "fixtures"} <= bedroom.keys()
    toilet = next(f for f in body["fixtures"] if f["kind"] == "toilet")
    assert {"kind", "room", "polygon_px", "polygon_m", "outline_source"} <= toilet.keys()
    assert body["fixtures"].index(toilet) in body["rooms"][toilet["room"]]["fixtures"]
    assert toilet["space"]["kind"] == "transfer"
    assert body["accessible_wc"] in (True, False)


def test_corrections_survive_a_reload(make_api, tmp_path):
    api = make_api()
    plan_id, _ = _open(api, _png_upload())
    sent = [{"kind": "wall", "start": [10.0, 10.0], "end": [50.0, 10.0]},
            {"kind": "merge", "point": [5.0, 5.0], "target_point": [20.0, 20.0]},
            {"kind": "remove_fixture", "point": [30.0, 40.0]}]

    saved = api.post(f"/plans/{plan_id}/sheets/0/corrections", json={"corrections": sent})

    assert saved.status_code == 200
    assert saved.json()["corrections"] == sent
    # A fresh app over the same folder is a reload: the corrections are still there.
    reloaded = TestClient(create_app(data_dir=tmp_path, model_client=lambda: _model_client()))
    assert reloaded.get(f"/plans/{plan_id}/sheets/0/corrections").json() == {"corrections": sent}
    assert reloaded.get(f"/plans/{plan_id}/sheets/0").json()["corrections"] == sent


def test_a_bad_correction_is_a_400(make_api):
    api = make_api()
    plan_id, _ = _open(api, _png_upload())

    response = api.post(f"/plans/{plan_id}/sheets/0/corrections", json={"corrections": [{"kind": "bogus"}]})

    assert response.status_code == 400


@pytest.mark.skipif(not SAMPLE.exists(), reason="private sample plan not present")
def test_sample_plan_rooms_carry_turning_verdicts(make_api):
    upload = {"file": ("plan.pdf", SAMPLE.read_bytes(), "application/pdf")}

    body = _open(make_api(), upload)[1].json()

    assert body["rooms"]
    for room in body["rooms"]:
        assert room["conforme"] in (True, False)
        assert room["verdict"].startswith(("Conforme PMR", "Non conforme PMR"))
        assert room["max_diameter_m"] > 0
    assert any(room["conforme"] for room in body["rooms"])


# --- dossiers (issue #11) --------------------------------------------------------------

def _dossier_upload():
    """A plan de masse, the RDC and an untitled sheet on a page of its own size."""
    doc = pymupdf.open()
    for title, size in [("PLAN DE MASSE", (842, 595)), ("PLAN DU RDC", (842, 595)), (None, (595, 842))]:
        page = doc.new_page(width=size[0], height=size[1])
        if title:
            page.insert_text((40, 60), title, fontsize=24)
    return {"file": ("dossier.pdf", doc.tobytes(), "application/pdf")}


def _counting_api(tmp_path):
    calls = []
    return TestClient(create_app(data_dir=tmp_path, model_client=lambda: _model_client(calls=calls))), calls


def test_uploading_a_building_lists_its_sheets_without_a_model_call(tmp_path):
    api, calls = _counting_api(tmp_path)

    body = api.post("/plans", files=_dossier_upload()).json()

    assert [(s["page"], s["name"], s["annexe"]) for s in body["sheets"]] == [
        (0, "Plan de masse", True), (1, "RDC", False), (2, "Page 3", False)]
    assert api.get(f"/plans/{body['id']}").json() == body
    assert calls == []


def test_a_sheet_is_read_from_its_own_page_and_only_once(tmp_path):
    api, calls = _counting_api(tmp_path)
    plan_id = api.post("/plans", files=_dossier_upload()).json()["id"]

    third = api.get(f"/plans/{plan_id}/sheets/2").json()
    again = api.get(f"/plans/{plan_id}/sheets/2").json()

    assert (third["page"], third["name"], third["checked"]) == (2, "Page 3", True)
    assert third["height"] > third["width"]  # page 3 is the portrait one
    assert again == third
    assert calls.count("Rooms") == 1
    image = api.get(f"/plans/{plan_id}/sheets/2/image")
    assert Image.open(io.BytesIO(image.content)).size == (third["width"], third["height"])


def test_a_plan_annexe_answers_why_it_is_not_checked_without_a_model_call(tmp_path):
    api, calls = _counting_api(tmp_path)
    plan_id = api.post("/plans", files=_dossier_upload()).json()["id"]

    body = api.get(f"/plans/{plan_id}/sheets/0").json()

    assert body["annexe"] and not body["checked"]
    assert "plan annexe" in body["reason"]
    assert body["rooms"] == [] and calls == []
    assert api.post(f"/plans/{plan_id}/sheets/0/corrections", json={"corrections": []}).status_code == 409


def test_each_sheet_keeps_its_own_corrections(make_api):
    api = make_api()
    plan_id = api.post("/plans", files=_dossier_upload()).json()["id"]
    api.get(f"/plans/{plan_id}/sheets/1")
    api.get(f"/plans/{plan_id}/sheets/2")
    sent = [{"kind": "remove_fixture", "point": [30.0, 40.0]}]

    api.post(f"/plans/{plan_id}/sheets/2/corrections", json={"corrections": sent})

    assert api.get(f"/plans/{plan_id}/sheets/2/corrections").json() == {"corrections": sent}
    assert api.get(f"/plans/{plan_id}/sheets/1/corrections").json() == {"corrections": []}


def test_a_sheet_is_corrected_only_once_it_was_opened(make_api):
    api = make_api()
    plan_id = api.post("/plans", files=_dossier_upload()).json()["id"]

    response = api.post(f"/plans/{plan_id}/sheets/1/corrections", json={"corrections": []})

    assert response.status_code == 409


def test_a_broken_pdf_is_a_400_and_leaves_nothing_behind(tmp_path):
    api = TestClient(create_app(data_dir=tmp_path, model_client=lambda: _model_client()))

    response = api.post("/plans", files={"file": ("plan.pdf", b"%PDF-nope", "application/pdf")})

    assert response.status_code == 400
    assert list(tmp_path.iterdir()) == []


# --- the check streams its stages (issue #12) ------------------------------------------

STREAM = {"Accept": "application/x-ndjson"}


def _lines(response):
    import json
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_a_streamed_sheet_reports_its_stages_then_the_same_result(tmp_path):
    api, _ = _counting_api(tmp_path)
    plan_id = api.post("/plans", files=_png_upload()).json()["id"]

    streamed = api.get(f"/plans/{plan_id}/sheets/0", headers=STREAM)

    assert streamed.headers["content-type"].startswith("application/x-ndjson")
    lines = _lines(streamed)
    stages = [line["stage"] for line in lines if "stage" in line]
    assert stages[0] == "reading" and "segmenting" in stages
    assert "result" in lines[-1]
    assert lines[-1]["result"] == api.get(f"/plans/{plan_id}/sheets/0").json()


def test_a_stored_sheet_streams_its_result_at_once(make_api):
    api = make_api()
    plan_id, first = _open(api, _png_upload())

    lines = _lines(api.get(f"/plans/{plan_id}/sheets/0", headers=STREAM))

    assert lines == [{"result": first.json()}]


def test_a_streamed_failure_ends_with_an_error_line(make_api):
    api = make_api(error=RuntimeError("rate limited"))
    plan_id = api.post("/plans", files=_png_upload()).json()["id"]

    lines = _lines(api.get(f"/plans/{plan_id}/sheets/0", headers=STREAM))

    assert lines[-1]["status"] == 502 and "rate limited" in lines[-1]["error"]
    assert not any("result" in line for line in lines)


def test_an_unknown_sheet_is_still_a_404_when_streamed(make_api):
    api = make_api()
    plan_id = api.post("/plans", files=_png_upload()).json()["id"]

    assert api.get(f"/plans/{plan_id}/sheets/5", headers=STREAM).status_code == 404


def test_a_long_stage_keeps_the_stream_alive(tmp_path):
    import time

    def slow_client():
        client = _model_client()
        create = client.chat.completions.create

        def slow(**kwargs):
            time.sleep(0.3)
            return create(**kwargs)

        client.chat.completions.create = slow
        return client

    api = TestClient(create_app(data_dir=tmp_path, model_client=slow_client, heartbeat_s=0.05))
    plan_id = api.post("/plans", files=_png_upload()).json()["id"]

    lines = _lines(api.get(f"/plans/{plan_id}/sheets/0", headers=STREAM))

    assert {"heartbeat": True} in lines
    assert "result" in lines[-1]


def test_a_corrections_replay_streams_too(make_api):
    api = make_api()
    plan_id, _ = _open(api, _png_upload())
    sent = [{"kind": "remove_fixture", "point": [30.0, 40.0]}]

    lines = _lines(api.post(f"/plans/{plan_id}/sheets/0/corrections", json={"corrections": sent},
                            headers=STREAM))

    assert lines[-1]["result"]["corrections"] == sent
    assert any(line.get("stage") == "segmenting" for line in lines)


@pytest.mark.skipif(not SAMPLE.exists(), reason="private sample plan not present")
def test_a_vector_sheet_comes_back_with_its_doors(make_api):
    upload = {"file": ("plan.pdf", SAMPLE.read_bytes(), "application/pdf")}

    body = _open(make_api(), upload)[1].json()

    assert body["doors"] and body["doors_ok"] in (True, False)
    door = body["doors"][0]
    assert {"rooms", "role", "width_m", "measured_m", "required_m", "ok", "verdict",
            "doorway_px", "swing_px"} <= door.keys()
    assert all("doors" in room for room in body["rooms"])


def test_a_picture_sheet_has_no_doors(make_api):
    body = _open(make_api(), _png_upload())[1].json()

    assert body["doors"] == [] and body["doors_ok"] is None


# --- walk the plan (issue #14) ---------------------------------------------------------

def test_a_sheet_carries_its_walk_and_can_be_walked_again_without_a_model_call(tmp_path):
    api, calls = _counting_api(tmp_path)
    plan_id, opened = _open(api, _png_upload())
    asked = len(calls)

    assert "walk" in opened.json()
    again = api.get(f"/plans/{plan_id}/sheets/0/walk")

    assert again.status_code == 200 and again.json() == opened.json()["walk"]
    assert len(calls) == asked


def test_walking_from_a_room_that_is_not_there_is_a_400(make_api):
    api = make_api()
    plan_id, _ = _open(api, _png_upload())

    assert api.get(f"/plans/{plan_id}/sheets/0/walk", params={"from": 99}).status_code == 400


def test_walking_a_sheet_not_opened_yet_is_a_409(make_api):
    api = make_api()
    plan_id = api.post("/plans", files=_png_upload()).json()["id"]

    assert api.get(f"/plans/{plan_id}/sheets/0/walk").status_code == 409


@pytest.mark.skipif(not SAMPLE.exists(), reason="private sample plan not present")
def test_sample_plan_walked_from_a_room_reaches_its_neighbours(make_api):
    api = make_api()
    upload = {"file": ("plan.pdf", SAMPLE.read_bytes(), "application/pdf")}
    plan_id, opened = _open(api, upload)
    body = opened.json()
    corridor = max(range(len(body["rooms"])), key=lambda i: len(body["rooms"][i]["doors"]))

    walked = api.get(f"/plans/{plan_id}/sheets/0/walk", params={"from": corridor}).json()

    assert walked["start"] == {"room": corridor, "door": None}
    assert len(walked["reached"]) > len(body["rooms"][corridor]["doors"]) // 2
    assert walked["route"][0]["event"] == "start"
