import io
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from conformscope.api import create_app
from conformscope.client import MissingKeyError
from test_labels import RECORDED
from test_rooms import SAMPLE


def _model_client(reply=RECORDED, error=None):
    def create(**kwargs):
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


def test_upload_returns_the_rooms_muse_spark_read(make_api):
    response = make_api().post("/plans", files=_png_upload())

    assert response.status_code == 200
    body = response.json()
    assert (body["width"], body["height"]) == (1754, 1240)
    assert body["scale"] == "1:100"
    assert len(body["labels"]) == 8
    assert body["labels"][0] == {"name": "Bedroom", "room_type": "bedroom",
                                 "x": 203, "y": 213, "area_m2": 15.31}


def test_uploaded_plan_can_be_fetched_again_with_its_image(make_api):
    api = make_api()
    plan_id = api.post("/plans", files=_png_upload()).json()["id"]

    again = api.get(f"/plans/{plan_id}")
    image = api.get(f"/plans/{plan_id}/image")

    assert again.status_code == 200
    assert again.json() == api.get(f"/plans/{plan_id}").json()
    assert len(again.json()["labels"]) == 8
    assert image.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(image.content)).size == (1754, 1240)


def test_a_bad_model_reply_is_a_502_with_a_reason(make_api):
    response = make_api(reply="Sorry, I can't read this plan.").post("/plans", files=_png_upload())

    assert response.status_code == 502
    assert "JSON" in response.json()["detail"]


def test_a_failed_model_call_is_a_502_with_a_reason(make_api):
    response = make_api(error=RuntimeError("rate limited")).post("/plans", files=_png_upload())

    assert response.status_code == 502
    assert "rate limited" in response.json()["detail"]


def test_an_unsupported_file_is_a_400(make_api):
    response = make_api().post("/plans", files={"file": ("plan.docx", b"nope", "application/octet-stream")})

    assert response.status_code == 400


def test_an_unknown_plan_is_a_404(make_api):
    api = make_api()

    assert api.get("/plans/does-not-exist").status_code == 404
    assert api.get("/plans/..%2F..%2Fetc/image").status_code == 404


def test_a_missing_key_is_a_503_that_says_so(tmp_path):
    def no_key():
        raise MissingKeyError("MODEL_API_KEY is not set.")

    api = TestClient(create_app(data_dir=tmp_path, model_client=no_key))

    response = api.post("/plans", files=_png_upload())

    assert response.status_code == 503
    assert "MODEL_API_KEY" in response.json()["detail"]
    assert list(tmp_path.iterdir()) == []


def test_a_picture_with_no_sam_answer_still_returns_its_labels_with_a_warning(make_api):
    # The fake client has no SAM endpoint, so segmenting fails; the upload must not.
    body = make_api().post("/plans", files=_png_upload()).json()

    assert body["kind"] == "picture"
    assert body["rooms"] == []
    assert any("SAM 3.1" in w for w in body["warnings"])
    assert body["fixtures"] == [] and body["accessible_wc"] is None


@pytest.mark.skipif(not SAMPLE.exists(), reason="private sample plan not present")
def test_a_vector_plan_comes_back_with_measured_rooms(make_api):
    upload = {"file": ("plan.pdf", SAMPLE.read_bytes(), "application/pdf")}

    body = make_api().post("/plans", files=upload).json()

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
    plan_id = api.post("/plans", files=_png_upload()).json()["id"]
    sent = [{"kind": "wall", "start": [10.0, 10.0], "end": [50.0, 10.0]},
            {"kind": "merge", "point": [5.0, 5.0], "target_point": [20.0, 20.0]}]

    saved = api.post(f"/plans/{plan_id}/corrections", json={"corrections": sent})

    assert saved.status_code == 200
    assert saved.json()["corrections"] == sent
    # A fresh app over the same folder is a reload: the corrections are still there.
    reloaded = TestClient(create_app(data_dir=tmp_path, model_client=lambda: _model_client()))
    assert reloaded.get(f"/plans/{plan_id}/corrections").json() == {"corrections": sent}
    assert reloaded.get(f"/plans/{plan_id}").json()["corrections"] == sent


def test_a_bad_correction_is_a_400(make_api):
    api = make_api()
    plan_id = api.post("/plans", files=_png_upload()).json()["id"]

    response = api.post(f"/plans/{plan_id}/corrections", json={"corrections": [{"kind": "bogus"}]})

    assert response.status_code == 400


@pytest.mark.skipif(not SAMPLE.exists(), reason="private sample plan not present")
def test_sample_plan_rooms_carry_turning_verdicts(make_api):
    upload = {"file": ("plan.pdf", SAMPLE.read_bytes(), "application/pdf")}

    body = make_api().post("/plans", files=upload).json()

    assert body["rooms"]
    for room in body["rooms"]:
        assert room["conforme"] in (True, False)
        assert room["verdict"].startswith(("Conforme PMR", "Non conforme PMR"))
        assert room["max_diameter_m"] > 0
    assert any(room["conforme"] for room in body["rooms"])
