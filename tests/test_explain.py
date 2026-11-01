import json
from types import SimpleNamespace

from conformscope.explain import (
    collect_failures,
    explain_failures,
    explain_sheet,
    template_explanation,
    verify_failures,
)

BODY = {
    "rooms": [
        {"name": "WC", "room_type": "wc", "conforme": False, "max_diameter_m": 1.1,
         "verdict": "Non conforme PMR (max Ø1.10 m)"},
        {"name": "Living", "room_type": "living", "conforme": True, "max_diameter_m": 2.4,
         "verdict": "Conforme PMR"},
    ],
    "doors": [
        {"rooms": [0, 1], "width_m": 0.7, "required_m": 0.8, "ok": False,
         "verdict": "Too narrow"},
        {"rooms": [1, None], "width_m": 0.9, "required_m": 0.9, "ok": True,
         "verdict": "Wide enough"},
    ],
    "fixtures": [
        {"kind": "toilet", "room": 0,
         "space": {"kind": "transfer", "fits": False, "verdict": "No transfer space"}},
        {"kind": "placard", "room": 1, "space": None},
    ],
    "accessible_wc": False,
}


def _chat_client(content=None, tool_arguments=None, error=None):
    def create(**kwargs):
        if error:
            raise error
        if tool_arguments is not None:
            call = SimpleNamespace(function=SimpleNamespace(arguments=tool_arguments))
            message = SimpleNamespace(content=None, tool_calls=[call])
        else:
            message = SimpleNamespace(content=content, tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def test_collect_failures_covers_each_kind_and_skips_passes():
    failures = collect_failures(BODY)

    assert [f["kind"] for f in failures] == ["turning", "door", "transfer", "accessible_wc"]
    assert failures[0]["measured_m"] == 1.1 and failures[0]["required_m"] == 1.50
    assert failures[1]["subject"] == "Door WC \u2194 Living"
    assert failures[2]["subject"] == "toilet in WC"


def test_template_explanations_say_the_numbers():
    failures = collect_failures(BODY)

    turning = template_explanation(failures[0])
    door = template_explanation(failures[1])

    assert "\u00d81.10 m" in turning["reason"] and "\u00d81.50 m" in turning["reason"]
    assert "0.70 m" in door["reason"] and "0.80 m" in door["fix"]


def test_explain_without_a_model_uses_templates():
    explained, source = explain_failures(None, collect_failures(BODY))

    assert source == "template"
    assert all(f["reason"] and f["fix"] and f["source"] == "template" for f in explained)


def test_explain_parses_muse_spark_and_fills_gaps_with_templates():
    failures = collect_failures(BODY)
    reply = json.dumps({"explanations": [
        {"id": "turn-0", "reason": "Too small to turn.", "fix": "Make it bigger."}]})
    client = _chat_client(content=reply)

    explained, source = explain_failures(client, failures)

    assert source == "muse-spark"
    assert explained[0]["reason"] == "Too small to turn." and explained[0]["source"] == "muse-spark"
    assert explained[1]["source"] == "template"  # the id Muse Spark skipped


def test_explain_falls_back_when_the_model_call_fails():
    explained, source = explain_failures(
        _chat_client(error=RuntimeError("down")), collect_failures(BODY))

    assert source == "template" and all(f["reason"] for f in explained)


def test_verify_flags_disagreement_and_low_confidence_as_doubtful():
    failures = collect_failures(BODY)
    checks = json.dumps({"checks": [
        {"id": "turn-0", "agree": True, "confidence": 0.95, "note": "Numbers agree."},
        {"id": "door-0", "agree": False, "confidence": 0.9, "note": "Width misread?"},
        {"id": "space-0", "agree": True, "confidence": 0.5, "note": "Unsure."},
    ]})

    verified = verify_failures(_chat_client(tool_arguments=checks), failures)

    assert verified["turn-0"]["doubtful"] is False
    assert verified["door-0"]["doubtful"] is True
    assert verified["space-0"]["doubtful"] is True
    assert "accessible-wc" not in verified  # the check the verifier skipped


def test_verify_without_a_client_or_on_failure_is_empty():
    failures = collect_failures(BODY)

    assert verify_failures(None, failures) == {}
    assert verify_failures(_chat_client(error=RuntimeError("down")), failures) == {}


def test_explain_sheet_marks_unverified_failures():
    result = explain_sheet(None, None, BODY)

    assert result["explained_by"] == "template" and result["verified_by"] is None
    assert all(f["verify"] == {"status": "not_verified"} for f in result["failures"])


def test_explain_sheet_never_touches_a_verdict():
    before = json.dumps(BODY, sort_keys=True)

    explain_sheet(None, None, BODY)

    assert json.dumps(BODY, sort_keys=True) == before
