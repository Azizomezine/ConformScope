"""HTTP API: upload a plan, get back the rooms Muse Spark read on it.

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
from conformscope.labels import read_rooms
from conformscope.plan import load_plan

PLAN_ID = re.compile(r"[0-9a-f]{32}")


def create_app(data_dir: str | Path = ".data/plans", model_client: Callable = make_client) -> FastAPI:
    data_dir = Path(data_dir)
    app = FastAPI(title="ConformScope")

    def plan_dir(plan_id: str) -> Path:
        folder = data_dir / plan_id
        if not PLAN_ID.fullmatch(plan_id) or not (folder / "reading.json").exists():
            raise HTTPException(404, "Unknown plan")
        return folder

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
                raw, reading = read_rooms(model_client(), plan)
            except MissingKeyError as error:
                raise HTTPException(503, str(error)) from error
            except ValueError as error:
                raise HTTPException(502, str(error)) from error
            except Exception as error:
                raise HTTPException(502, f"Muse Spark call failed: {error}") from error
            (folder / "muse_rooms.json").write_text(raw, encoding="utf-8")
        except BaseException:
            shutil.rmtree(folder, ignore_errors=True)
            raise

        body = {"id": plan_id, "width": plan.width, "height": plan.height,
                "scale": reading.scale, "rooms": [asdict(room) for room in reading.rooms]}
        (folder / "reading.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        return body

    @app.get("/plans/{plan_id}")
    def get_plan(plan_id: str) -> dict:
        return json.loads((plan_dir(plan_id) / "reading.json").read_text(encoding="utf-8"))

    @app.get("/plans/{plan_id}/image")
    def get_plan_image(plan_id: str) -> FileResponse:
        return FileResponse(plan_dir(plan_id) / "plan.png", media_type="image/png")

    return app


app = create_app()
