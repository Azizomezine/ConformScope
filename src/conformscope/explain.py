"""Explain + verify: a human sentence for every failure, and a second opinion (issue #16).

The geometry decides every verdict; this module never changes one. It collects the
failures a checked sheet already carries -- turning circle, door width, transfer and
washbasin spaces, accessible WC -- and:

- explains each in plain language: Muse Spark (`labels.MODEL`) writes the reason and
  the fix in one text call, answered as JSON against a schema. With no model, or a
  failed call, a deterministic template writes the same shape from the measured
  numbers, so a sheet is never left unexplained for want of a key;
- verifies each verdict: Muse Spark Open on Baseten re-checks the numbers through one
  forced tool call (Baseten has no JSON mode; see docs/research/meta-hackathon-stack.md
  section 5). A disagreement, or a confidence under `DOUBT_CONFIDENCE`, flags the
  failure **doubtful** for the auditor. With no verifier the failures are
  `not_verified`, never an error.

Pure on the sheet body as the API returns it, so a stored sheet can be explained
again without measuring it again.
"""

from __future__ import annotations

import json

import jsonschema

from conformscope.client import VERIFIER_MODEL
from conformscope.labels import MODEL

DOUBT_CONFIDENCE = 0.70  # under this, the verifier's agreement is too weak to trust
MIN_TURNING_M = 1.50


def _room_name(body: dict, index: int | None) -> str:
    rooms = body.get("rooms", [])
    if index is None or not 0 <= index < len(rooms):
        return "a room"
    return rooms[index].get("name") or f"Room {index + 1}"


def collect_failures(body: dict) -> list[dict]:
    """Every failing verdict on a checked sheet, with the numbers that decided it."""
    failures: list[dict] = []
    for i, room in enumerate(body.get("rooms", [])):
        if room.get("conforme") is False:
            failures.append({
                "id": f"turn-{i}", "kind": "turning", "room": i, "door": None, "fixture": None,
                "subject": _room_name(body, i), "verdict": room.get("verdict"),
                "measured_m": room.get("max_diameter_m"), "required_m": MIN_TURNING_M})
    for i, door in enumerate(body.get("doors", [])):
        if door.get("ok") is False:
            sides = " ↔ ".join("outside the rooms" if r is None else _room_name(body, r)
                                 for r in door.get("rooms", []))
            failures.append({
                "id": f"door-{i}", "kind": "door", "room": None, "door": i, "fixture": None,
                "subject": f"Door {sides}", "verdict": door.get("verdict"),
                "measured_m": door.get("width_m"), "required_m": door.get("required_m")})
    for i, fixture in enumerate(body.get("fixtures", [])):
        space = fixture.get("space")
        if space and space.get("fits") is False:
            failures.append({
                "id": f"space-{i}", "kind": space["kind"], "room": fixture.get("room"),
                "door": None, "fixture": i,
                "subject": f"{fixture['kind']} in {_room_name(body, fixture.get('room'))}",
                "verdict": space.get("verdict"), "measured_m": None, "required_m": None})
    if body.get("accessible_wc") is False:
        failures.append({
            "id": "accessible-wc", "kind": "accessible_wc", "room": None, "door": None,
            "fixture": None, "subject": "The home",
            "verdict": "No toilet has a 0.80 × 1.30 m transfer space",
            "measured_m": None, "required_m": None})
    return failures


def template_explanation(failure: dict) -> dict:
    """The reason and the fix from the measured numbers alone; no model needed."""
    kind, measured, required = failure["kind"], failure["measured_m"], failure["required_m"]
    subject = failure["subject"]
    if kind == "turning":
        return {"reason": f"{subject} is too tight to turn in: the biggest circle the free "
                          f"floor holds is Ø{measured:.2f} m, under the Ø{required:.2f} m a "
                          "wheelchair needs to turn around.",
                "fix": "Free up floor in the room — move a fixture, widen the room, or "
                       "merge it with the space next door — until a Ø1.50 m circle fits."}
    if kind == "door":
        return {"reason": f"{subject} is {measured:.2f} m wide, under the "
                          f"{required:.2f} m needed to get a wheelchair through.",
                "fix": f"Widen the doorway to at least {required:.2f} m (the next "
                       "standard door size up), checking the wall can take it."}
    if kind == "transfer":
        return {"reason": f"The {failure['subject']} leaves no free 0.80 × 1.30 m rectangle "
                          "touching the toilet, so a wheelchair cannot park beside it to transfer.",
                "fix": "Clear a 0.80 × 1.30 m space beside the toilet: move whatever stands "
                       "there, or turn the toilet so the space beside it is free."}
    if kind == "washbasin":
        return {"reason": f"The {failure['subject']} leaves no free 0.80 × 1.30 m rectangle "
                          "in front of the washbasin, so a wheelchair cannot face it.",
                "fix": "Clear a 0.80 × 1.30 m space in front of the washbasin so a "
                       "wheelchair can roll up to it."}
    return {"reason": "No toilet in the home has the 0.80 × 1.30 m transfer space beside "
                      "it, so there is no accessible WC.",
            "fix": "Give one toilet a free 0.80 × 1.30 m space beside it — usually the "
                   "bathroom toilet, by moving a fixture or enlarging the room."}


EXPLAIN_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["explanations"],
    "properties": {"explanations": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["id", "reason", "fix"],
        "properties": {"id": {"type": "string"}, "reason": {"type": "string"},
                       "fix": {"type": "string"}}}}},
}

EXPLAIN_PROMPT = (
    "You explain French wheelchair-accessibility (PMR) failures on a home plan to the "
    "family who will live there. For each failure, in plain language with no jargon: "
    "reason = why it fails, from the measured numbers; fix = the smallest change on the "
    "plan that would make it pass. One or two short sentences each. Never change or "
    "question the verdict itself.\n\nFailures:\n"
)


def _parse_explanations(text: str) -> dict[str, dict]:
    data = json.loads(text)
    jsonschema.validate(data, EXPLAIN_SCHEMA)
    return {item["id"]: {"reason": item["reason"], "fix": item["fix"]}
            for item in data["explanations"]}


def explain_failures(client, failures: list[dict]) -> tuple[list[dict], str]:
    """Each failure with its reason and fix; `client=None` means templates throughout."""
    written: dict[str, dict] = {}
    source = "template"
    if client is not None and failures:
        try:
            facts = [{key: failure[key] for key in
                      ("id", "kind", "subject", "verdict", "measured_m", "required_m")}
                     for failure in failures]
            response = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": EXPLAIN_PROMPT + json.dumps(facts)}],
                response_format={"type": "json_schema", "json_schema": {
                    "name": "Explanations", "schema": EXPLAIN_SCHEMA}},
            )
            written = _parse_explanations(response.choices[0].message.content)
            source = "muse-spark"
        except Exception:
            written, source = {}, "template"
    return [{**failure, **written.get(failure["id"], template_explanation(failure)),
             "source": "muse-spark" if failure["id"] in written else "template"}
            for failure in failures], source


VERIFY_TOOL = {
    "type": "function",
    "function": {
        "name": "report_verification",
        "description": "Report, per failure id, whether the geometric verdict agrees "
                       "with its measured numbers, and how confident you are.",
        "parameters": {
            "type": "object", "additionalProperties": False, "required": ["checks"],
            "properties": {"checks": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["id", "agree", "confidence", "note"],
                "properties": {"id": {"type": "string"}, "agree": {"type": "boolean"},
                               "confidence": {"type": "number"},
                               "note": {"type": "string"}}}}},
        },
    },
}

VERIFY_PROMPT = (
    "You are a verifier agent double-checking wheelchair-accessibility (PMR) verdicts "
    "that geometry computed from a home plan. For each failure, judge only whether the "
    "verdict follows from its measured numbers (turning needs a Ø1.50 m circle; a door "
    "needs its required width; a transfer or washbasin space needs a free "
    "0.80 × 1.30 m rectangle). Answer by calling report_verification once, with a "
    "confidence from 0 to 1 and a one-line note.\n\nFailures:\n"
)


def _parse_verification(response) -> dict[str, dict]:
    calls = response.choices[0].message.tool_calls or []
    if not calls:
        return {}
    data = json.loads(calls[0].function.arguments)
    return {check["id"]: check for check in data["checks"]}


def verify_failures(client, failures: list[dict]) -> dict[str, dict]:
    """A verifier opinion per failure id; empty when there is no verifier or it fails.

    Baseten serves Muse Spark Open with no JSON mode, so the answer is one forced
    tool call, validated by hand.
    """
    if client is None or not failures:
        return {}
    try:
        facts = [{key: failure[key] for key in
                  ("id", "kind", "subject", "verdict", "measured_m", "required_m")}
                 for failure in failures]
        response = client.chat.completions.create(
            model=VERIFIER_MODEL,
            messages=[{"role": "user", "content": VERIFY_PROMPT + json.dumps(facts)}],
            tools=[VERIFY_TOOL],
            tool_choice={"type": "function", "function": {"name": "report_verification"}},
        )
        checks = _parse_verification(response)
    except Exception:
        return {}
    return {failure["id"]: {
        "status": "verified",
        "agree": bool(check["agree"]),
        "confidence": round(float(check["confidence"]), 2),
        "note": check["note"],
        "doubtful": (not check["agree"]) or float(check["confidence"]) < DOUBT_CONFIDENCE,
    } for failure in failures if (check := checks.get(failure["id"]))}


def explain_sheet(model_client, verifier_client, body: dict) -> dict:
    """The sheet's failures, explained and verified. The verdicts are never touched."""
    failures = collect_failures(body)
    explained, source = explain_failures(model_client, failures)
    checks = verify_failures(verifier_client, failures)
    for failure in explained:
        failure["verify"] = checks.get(failure["id"], {"status": "not_verified"})
    return {"failures": explained, "explained_by": source,
            "verified_by": VERIFIER_MODEL if checks else None}
