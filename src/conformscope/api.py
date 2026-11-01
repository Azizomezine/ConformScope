"""HTTP API: upload a building's plans, then open each sheet to get back its rooms, read by
Muse Spark and measured in metres.

    uv run uvicorn conformscope.api:app --reload

An upload is a **dossier**, one **sheet** per page (issue #11). The upload only reads the
sheets' printed titles, so it answers at once; a sheet is checked -- the Muse Spark
reading, then the measuring -- the first time it is opened, and kept.

A check takes minutes on a big sheet, so it can stream its stages (issue #12): a client
sending `Accept: application/x-ndjson` gets one JSON line per stage as it starts, a
heartbeat line while a long stage runs (a proxy drops a silent connection), then
`{"result": ...}` or `{"error": ..., "status": ...}`. Without that header the answer is
the plain JSON body.
"""

from __future__ import annotations

import json
import queue
import re
import shutil
import threading
import uuid
from collections.abc import Callable, Iterator
from dataclasses import asdict
from pathlib import Path

import pymupdf  # type: ignore[import-untyped]
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse

from conformscope.client import MissingKeyError, make_client, make_verifier_client
from conformscope.explain import explain_sheet
from conformscope.corrections import (
    apply_overrides,
    corrections_from_data,
    corrections_to_data,
    corrections_to_jsonl,
    dump_corrections,
    dump_labels,
    load_corrections,
)
from conformscope.labels import RoomLabel, RoomReading, read_rooms
from conformscope.plan import IMAGE_SUFFIXES, load_plan
from conformscope.rooms import measure_rooms
from conformscope.sheets import read_sheets
from conformscope.turning import check_turning
from conformscope.walk import walk

PLAN_ID = re.compile(r"[0-9a-f]{32}")
ANNEXE_REASON = "Not checked: a plan annexe (masse, situation, toiture or combles)"
NDJSON = "application/x-ndjson"
HEARTBEAT_S = 15.0  # well inside the web proxy's 120 s idle limit

Work = Callable[[Callable[[dict], None]], dict]  # told each stage, answers the body


def _line(event: dict) -> bytes:
    return (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")


def stream(work: Work, heartbeat_s: float) -> Iterator[bytes]:
    """Run `work` on its own thread and pass on each stage it reports as it starts."""
    events: queue.Queue = queue.Queue()

    def run():
        try:
            events.put(("result", work(lambda event: events.put(("stage", event)))))
        except HTTPException as error:
            events.put(("error", {"error": str(error.detail), "status": error.status_code}))
        except Exception as error:
            events.put(("error", {"error": str(error), "status": 500}))

    threading.Thread(target=run, daemon=True).start()
    while True:
        try:
            kind, value = events.get(timeout=heartbeat_s)
        except queue.Empty:
            yield _line({"heartbeat": True})
            continue
        if kind == "stage":
            yield _line(value)
        elif kind == "result":
            yield _line({"result": value})
            return
        else:
            yield _line(value)
            return


def enrich(rooms):
    """Issue #4: attach the turning-circle verdict to each measured room."""
    out = []
    for room in rooms:
        room = dict(room)
        polygon = room.get("polygon_m") or []
        if polygon:
            check = check_turning(polygon)
            room["conforme"] = check.conforme
            room["max_diameter_m"] = check.max_diameter_m
            room["center_m"] = list(check.center_m) if check.center_m else None
            room["verdict"] = check.verdict
        else:
            room["conforme"] = None
            room["max_diameter_m"] = None
            room["center_m"] = None
            room["verdict"] = None
        out.append(room)
    return out


def pt_per_plan_px(original: Path, plan, page: int) -> float | None:
    """PDF points per plan-image pixel, to anchor corrections (issue #6)."""
    if original.suffix.lower() != ".pdf" or not plan.width:
        return None
    try:
        with pymupdf.open(original) as doc:
            return doc[page].rect.width / plan.width
    except Exception:
        return None


def measured_body(measured) -> dict:
    rooms = enrich([asdict(room) for room in measured.rooms])
    return {"kind": measured.kind, "scale_source": measured.scale_source,
            "px_per_m": measured.px_per_m,
            "rooms": rooms,
            "walk": walk(rooms, measured.doors),
            "fixtures": [asdict(fixture) for fixture in measured.fixtures],
            "accessible_wc": measured.accessible_wc,
            "doors": measured.doors, "doors_ok": measured.doors_ok,
            "warnings": measured.warnings}


def create_app(data_dir: str | Path = ".data/plans", model_client: Callable = make_client,
               verifier_client: Callable = make_verifier_client,
               heartbeat_s: float = HEARTBEAT_S) -> FastAPI:
    data_dir = Path(data_dir)
    app = FastAPI(title="ConformScope")

    def answer(request: Request, work: Work):
        """The body as plain JSON, or its stages streamed when the client asks for them."""
        if NDJSON in request.headers.get("accept", ""):
            return StreamingResponse(stream(work, heartbeat_s), media_type=NDJSON)
        return work(lambda event: None)

    def dossier_dir(plan_id: str) -> Path:
        folder = data_dir / plan_id
        if not PLAN_ID.fullmatch(plan_id) or not (folder / "dossier.json").exists():
            raise HTTPException(404, "Unknown plan")
        return folder

    def dossier(folder: Path) -> dict:
        return json.loads((folder / "dossier.json").read_text(encoding="utf-8"))

    def sheet_of(plan_id: str, page: int) -> tuple[Path, Path, dict]:
        """The dossier's original file, the sheet's own folder, and the sheet."""
        folder = dossier_dir(plan_id)
        sheets = dossier(folder)["sheets"]
        if not 0 <= page < len(sheets):
            raise HTTPException(404, "Unknown sheet")
        own = folder / "sheets" / str(page)
        own.mkdir(parents=True, exist_ok=True)
        return next(folder.glob("original.*")), own, sheets[page]

    def sheet_image(original: Path, own: Path, page: int):
        plan = load_plan(original, page=page)
        (own / "plan.png").write_bytes(plan.png)
        return plan

    @app.post("/plans")
    def upload_plan(file: UploadFile) -> dict:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix != ".pdf" and suffix not in IMAGE_SUFFIXES:
            raise HTTPException(400, f"Unsupported plan file type: {suffix or file.filename}")
        plan_id = uuid.uuid4().hex
        folder = data_dir / plan_id
        folder.mkdir(parents=True)
        try:
            original = folder / ("original" + suffix)
            original.write_bytes(file.file.read())
            try:
                sheets = read_sheets(original)
                if suffix != ".pdf":
                    load_plan(original)  # a broken picture is refused here, not on opening
            except Exception as error:
                raise HTTPException(400, f"This file could not be read as a plan: {error}") from error
            if not sheets:
                raise HTTPException(400, "This PDF has no pages")
        except BaseException:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        body = {"id": plan_id, "sheets": [asdict(sheet) for sheet in sheets]}
        (folder / "dossier.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        return body

    @app.get("/plans/{plan_id}")
    def get_dossier(plan_id: str) -> dict:
        return dossier(dossier_dir(plan_id))

    @app.get("/plans/{plan_id}/sheets/{page}")
    def get_sheet(plan_id: str, page: int, request: Request):
        original, own, sheet = sheet_of(plan_id, page)
        return answer(request, lambda progress: check_sheet(plan_id, page, original, own, sheet, progress))

    def check_sheet(plan_id: str, page: int, original: Path, own: Path, sheet: dict,
                    progress: Callable[[dict], None]) -> dict:
        stored = own / "reading.json"
        if stored.exists():
            body = json.loads(stored.read_text(encoding="utf-8"))
            body["corrections"] = corrections_to_data(load_corrections(own))
            return body

        plan = sheet_image(original, own, page)
        head = {"id": plan_id, "page": page, "name": sheet["name"], "title": sheet["title"],
                "annexe": sheet["annexe"], "width": plan.width, "height": plan.height}
        if sheet["annexe"]:
            body = head | {"checked": False, "reason": ANNEXE_REASON, "scale": None, "labels": [],
                           "kind": None, "scale_source": None, "px_per_m": None, "rooms": [],
                           "fixtures": [], "accessible_wc": None, "doors": [], "doors_ok": None,
                           "walk": None, "warnings": [],
                           "pt_per_plan_px": None, "corrections": []}
            stored.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
            return body

        progress({"stage": "reading"})
        try:
            client = model_client()
            raw, reading = read_rooms(client, plan)
        except MissingKeyError as error:
            raise HTTPException(503, str(error)) from error
        except ValueError as error:
            raise HTTPException(502, str(error)) from error
        except Exception as error:
            raise HTTPException(502, f"Muse Spark call failed: {error}") from error
        (own / "muse_rooms.json").write_text(raw, encoding="utf-8")

        # The labels stand on their own: a sheet whose rooms cannot be measured is still
        # worth showing, with the reason.
        try:
            measured = measured_body(measure_rooms(client, original, plan, reading, page=page,
                                                   progress=progress))
        except Exception as error:
            measured = {"kind": None, "scale_source": None, "px_per_m": None, "rooms": [],
                        "fixtures": [], "accessible_wc": None, "doors": [], "doors_ok": None,
                        "walk": walk([], []),
                        "warnings": [f"The rooms could not be measured: {error}"]}

        body = head | {"checked": True, "reason": None, "scale": reading.scale,
                       "labels": [asdict(label) for label in reading.rooms]} | measured | {
                "pt_per_plan_px": pt_per_plan_px(original, plan, page), "corrections": []}
        stored.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        return body

    @app.get("/plans/{plan_id}/sheets/{page}/explain")
    def get_explain(plan_id: str, page: int) -> dict:
        """Explain and verify the stored sheet's failures (issue #16). Never measures
        again; with no key the explanations are templates and the verdicts unverified.
        The result is kept with the sheet, so a second opening costs no model call."""
        _, own, sheet = sheet_of(plan_id, page)
        stored = own / "reading.json"
        if not stored.exists():
            raise HTTPException(409, "Open the sheet before explaining it")
        body = json.loads(stored.read_text(encoding="utf-8"))
        if "explain" in body:
            return body["explain"]
        if sheet["annexe"]:
            result: dict = {"failures": [], "explained_by": None, "verified_by": None}
        else:
            def optional(factory):
                try:
                    return factory()
                except Exception:
                    return None

            result = explain_sheet(optional(model_client), optional(verifier_client), body)
        body["explain"] = result
        stored.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        return result

    @app.get("/plans/{plan_id}/sheets/{page}/walk")
    def get_walk(plan_id: str, page: int, request: Request) -> dict:
        """Walk the stored sheet again, from a room the auditor clicked (issue #14). Never
        measures again and never asks a model."""
        _, own, _ = sheet_of(plan_id, page)
        stored = own / "reading.json"
        if not stored.exists():
            raise HTTPException(409, "Open the sheet before walking it")
        body = json.loads(stored.read_text(encoding="utf-8"))
        rooms, doors = body.get("rooms", []), body.get("doors", [])
        start = request.query_params.get("from")
        if start is not None:
            if not start.isdigit() or int(start) >= len(rooms):
                raise HTTPException(400, f"No room {start} on this sheet")
            return walk(rooms, doors, int(start))
        return walk(rooms, doors)

    @app.get("/plans/{plan_id}/sheets/{page}/image")
    def get_sheet_image(plan_id: str, page: int) -> FileResponse:
        original, own, _ = sheet_of(plan_id, page)
        if not (own / "plan.png").exists():
            sheet_image(original, own, page)
        return FileResponse(own / "plan.png", media_type="image/png")

    @app.get("/plans/{plan_id}/sheets/{page}/corrections")
    def get_corrections(plan_id: str, page: int) -> dict:
        _, own, _ = sheet_of(plan_id, page)
        return {"corrections": corrections_to_data(load_corrections(own))}

    @app.get("/plans/{plan_id}/sheets/{page}/labels")
    def get_labels(plan_id: str, page: int) -> PlainTextResponse:
        _, own, _ = sheet_of(plan_id, page)
        return PlainTextResponse(
            corrections_to_jsonl(load_corrections(own),
                                 context=f"sheet {page + 1} of a dossier"),
            media_type="application/jsonl",
            headers={"Content-Disposition": f'attachment; filename="labels-{page}.jsonl"'})

    @app.post("/plans/{plan_id}/sheets/{page}/corrections")
    def post_corrections(plan_id: str, page: int, payload: dict, request: Request):
        original, own, sheet = sheet_of(plan_id, page)
        if sheet["annexe"]:
            raise HTTPException(409, ANNEXE_REASON)
        if not (own / "reading.json").exists():
            raise HTTPException(409, "Open the sheet before correcting it")
        try:
            parsed = corrections_from_data(payload.get("corrections", []))
        except (ValueError, KeyError, TypeError) as error:
            raise HTTPException(400, f"Bad corrections: {error}") from error
        dump_corrections(own, parsed)
        dump_labels(own, parsed, context=f"sheet {page + 1} of a dossier")
        return answer(request, lambda progress: replay(original, own, page, parsed, progress))

    def replay(original: Path, own: Path, page: int, parsed, progress: Callable[[dict], None]) -> dict:
        stored = json.loads((own / "reading.json").read_text(encoding="utf-8"))
        stored["corrections"] = corrections_to_data(parsed)
        # Replay the corrections on a fresh measure; stored rooms stand if it fails.
        try:
            plan = load_plan(original, page=page)
            reading = RoomReading(
                scale=stored.get("scale"),
                rooms=[RoomLabel(r["name"], r["room_type"], r["x"], r["y"], r.get("area_m2"))
                       for r in stored.get("labels", [])])
            measured = measure_rooms(model_client(), original, plan, reading,
                                     corrections=parsed, page=page, progress=progress)
            stored.update(measured_body(measured))
            stored.pop("explain", None)  # the failures moved; explain them afresh
            stored["pt_per_plan_px"] = pt_per_plan_px(original, plan, page)
        except MissingKeyError as error:
            raise HTTPException(503, str(error)) from error
        except Exception as error:
            stored["warnings"] = list(stored.get("warnings", [])) + [
                f"Corrections saved; the rooms could not be re-measured: {error}"]
        apply_overrides(stored, parsed)
        judged = [door["ok"] for door in stored.get("doors", []) if door.get("ok") is not None]
        stored["doors_ok"] = all(judged) if judged else None
        stored["walk"] = walk(stored.get("rooms", []), stored.get("doors", []))
        stored.pop("explain", None)  # the verdicts moved; explain them afresh
        (own / "reading.json").write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
        return stored

    return app


app = create_app()
