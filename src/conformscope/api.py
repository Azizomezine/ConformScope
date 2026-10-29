"""HTTP API: upload a plan, get back its rooms, read by Muse Spark and measured in metres.

    uv run uvicorn conformscope.api:app --reload
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse

from conformscope.client import MissingKeyError, make_client
from conformscope.corrections import (
    corrections_from_data,
    corrections_to_data,
    dump_corrections,
    load_corrections,
)
from conformscope.labels import RoomLabel, RoomReading, read_rooms
from conformscope.turning import check_turning


import pymupdf  # type: ignore[import-untyped]
from conformscope.plan import load_plan
from conformscope.rooms import measure_rooms

PLAN_ID = re.compile(r"[0-9a-f]{32}")


def create_app(data_dir: str | Path = ".data/plans", model_client: Callable = make_client) -> FastAPI:
    data_dir = Path(data_dir)
    app = FastAPI(title="ConformScope")

    def plan_dir(plan_id: str) -> Path:
        folder = data_dir / plan_id
        if not PLAN_ID.fullmatch(plan_id) or not (folder / "reading.json").exists():
            raise HTTPException(404, "Unknown plan")
        return folder

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

    def pt_per_plan_px(original: Path, plan) -> float | None:
        """PDF points per plan-image pixel, to anchor corrections (issue #6)."""
        if original.suffix.lower() != ".pdf" or not plan.width:
            return None
        try:
            with pymupdf.open(original) as doc:
                return doc[0].rect.width / plan.width
        except Exception:
            return None

    @app.post("/plans")
    def upload_plan(file: UploadFile) -> dict:
        plan_id = uuid.uuid4().hex
        folder = data_dir / plan_id
        folder.mkdir(parents=True)
        try:
            original = folder / ("original" + Path(file.filename or "").suffix.lower())
            original.write_bytes(file.file.read())
            try:
                plan = load_plan(original)
            except ValueError as error:
                raise HTTPException(400, str(error)) from error
            (folder / "plan.png").write_bytes(plan.png)

            try:
                client = model_client()
                raw, reading = read_rooms(client, plan)
            except MissingKeyError as error:
                raise HTTPException(503, str(error)) from error
            except ValueError as error:
                raise HTTPException(502, str(error)) from error
            except Exception as error:
                raise HTTPException(502, f"Muse Spark call failed: {error}") from error
            (folder / "muse_rooms.json").write_text(raw, encoding="utf-8")

            # The labels stand on their own: a plan whose rooms cannot be measured is still
            # worth showing, with the reason.
            try:
                measured = measure_rooms(client, original, plan, reading)
                kind, scale_source, px_per_m = measured.kind, measured.scale_source, measured.px_per_m
                rooms, warnings = enrich([asdict(room) for room in measured.rooms]), measured.warnings
                fixtures = [asdict(fixture) for fixture in measured.fixtures]
            except Exception as error:
                kind, scale_source, px_per_m, rooms, fixtures = None, None, None, [], []
                warnings = [f"The rooms could not be measured: {error}"]
        except BaseException:
            shutil.rmtree(folder, ignore_errors=True)
            raise

        body = {"id": plan_id, "width": plan.width, "height": plan.height,
                "scale": reading.scale, "labels": [asdict(label) for label in reading.rooms],
                "kind": kind, "scale_source": scale_source, "px_per_m": px_per_m,
                "rooms": rooms, "fixtures": fixtures, "warnings": warnings,
                "pt_per_plan_px": pt_per_plan_px(original, plan), "corrections": []}
        (folder / "reading.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        return body

    @app.get("/plans/{plan_id}")
    def get_plan(plan_id: str) -> dict:
        folder = plan_dir(plan_id)
        body = json.loads((folder / "reading.json").read_text(encoding="utf-8"))
        body["corrections"] = corrections_to_data(load_corrections(folder))
        return body

    @app.get("/plans/{plan_id}/image")
    def get_plan_image(plan_id: str) -> FileResponse:
        return FileResponse(plan_dir(plan_id) / "plan.png", media_type="image/png")

    @app.get("/plans/{plan_id}/corrections")
    def get_corrections(plan_id: str) -> dict:
        return {"corrections": corrections_to_data(load_corrections(plan_dir(plan_id)))}

    @app.post("/plans/{plan_id}/corrections")
    def post_corrections(plan_id: str, payload: dict) -> dict:
        folder = plan_dir(plan_id)
        try:
            parsed = corrections_from_data(payload.get("corrections", []))
        except (ValueError, KeyError, TypeError) as error:
            raise HTTPException(400, f"Bad corrections: {error}") from error
        dump_corrections(folder, parsed)
        stored = json.loads((folder / "reading.json").read_text(encoding="utf-8"))
        stored["corrections"] = corrections_to_data(parsed)
        # Replay the corrections on a fresh measure; stored rooms stand if it fails.
        try:
            original = next(folder.glob("original.*"))
            plan = load_plan(original)
            reading = RoomReading(
                scale=stored.get("scale"),
                rooms=[RoomLabel(r["name"], r["room_type"], r["x"], r["y"], r.get("area_m2"))
                       for r in stored.get("labels", [])])
            measured = measure_rooms(model_client(), original, plan, reading, corrections=parsed)
            stored.update({"kind": measured.kind, "scale_source": measured.scale_source,
                           "px_per_m": measured.px_per_m,
                           "rooms": enrich([asdict(r) for r in measured.rooms]),
                           "fixtures": [asdict(f) for f in measured.fixtures],
                           "warnings": measured.warnings,
                           "pt_per_plan_px": pt_per_plan_px(original, plan)})
        except MissingKeyError as error:
            raise HTTPException(503, str(error)) from error
        except Exception as error:
            stored["warnings"] = list(stored.get("warnings", [])) + [
                f"Corrections saved; the rooms could not be re-measured: {error}"]
        (folder / "reading.json").write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
        return stored

    return app


app = create_app()
