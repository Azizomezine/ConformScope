import json
from types import SimpleNamespace

from PIL import Image

from conformscope.spike import run_spike
from test_segment import SAMPLE


def _fake_client(sam_calls):
    rooms = {"scale": "1:100", "rooms": [
        {"name": "Séjour", "area_m2": 24.0, "room_type": "living", "x": 750, "y": 720},
    ]}

    def chat_create(**kwargs):
        message = SimpleNamespace(content=json.dumps(rooms))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    def sam_create(**kwargs):
        sam_calls.append(kwargs["input"][0]["content"][0]["text"])
        return SimpleNamespace(output_text=SAMPLE)

    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=chat_create)),
        responses=SimpleNamespace(create=sam_create),
    )


def test_spike_writes_every_output_for_one_plan(tmp_path):
    plan_path = tmp_path / "plan.png"
    Image.new("RGB", (320, 334), "white").save(plan_path)
    sam_calls = []

    out = run_spike(_fake_client(sam_calls), plan_path, tmp_path / "out")

    assert sam_calls[0] == "room"
    assert sam_calls[1].startswith("<0f>0<|point;")
    for name in ["rooms.json", "sam_concept.txt", "sam_points.txt",
                 "overlay_concept.png", "overlay_points.png", "summary.json"]:
        assert (out / name).exists(), name
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["labels"] == 1
    assert summary["concept_masks"] == 1
    assert summary["point_masks"] == 1
    assert Image.open(out / "overlay_points.png").size == (320, 334)


def test_spike_skips_point_prompts_when_no_labels_are_found(tmp_path):
    plan_path = tmp_path / "plan.png"
    Image.new("RGB", (100, 100), "white").save(plan_path)
    client = _fake_client([])
    client.chat.completions.create = lambda **kw: SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=json.dumps({"scale": None, "rooms": []})))])

    out = run_spike(client, plan_path, tmp_path / "out")

    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["point_masks"] == 0
    assert not (out / "sam_points.txt").exists()


def test_a_failing_sam_step_is_recorded_and_the_spike_carries_on(tmp_path):
    plan_path = tmp_path / "plan.png"
    Image.new("RGB", (320, 334), "white").save(plan_path)
    client = _fake_client([])
    concept = client.responses.create

    def sam_create(**kwargs):
        if kwargs["input"][0]["content"][0]["text"] != "room":
            raise RuntimeError("400 bad object prompt")
        return concept(**kwargs)

    client.responses.create = sam_create

    out = run_spike(client, plan_path, tmp_path / "out")

    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["concept_masks"] == 1
    assert summary["point_masks"] == 0
    assert summary["errors"] == {"points": "RuntimeError: 400 bad object prompt"}
    assert (out / "overlay_points.png").exists()
