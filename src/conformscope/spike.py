"""Spike for issue #1: can SAM 3.1 segment rooms on an architectural line drawing?

    uv run conformscope-spike <plan.pdf|plan.png> [--out .data/spike]

Runs Muse Spark (room labels) and SAM 3.1 (concept "room", then one point per label)
on one plan, and writes the raw replies and overlay PNGs for a human to judge.
"""

from __future__ import annotations

import argparse
import colorsys
import io
import json
import os
from dataclasses import asdict
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageDraw

from conformscope.labels import RoomLabel, read_rooms
from conformscope.plan import Plan, load_plan
from conformscope.segment import Mask, point_prompt, segment

BASE_URL = "https://api.meta.ai/v1"


def make_client() -> OpenAI:
    load_dotenv()
    key = os.environ.get("MODEL_API_KEY")
    if not key:
        raise SystemExit("MODEL_API_KEY is not set. Copy .env.example to .env and fill it in.")
    return OpenAI(base_url=BASE_URL, api_key=key)


def draw_overlay(plan: Plan, masks: list[Mask], labels: list[RoomLabel]) -> Image.Image:
    base = Image.open(io.BytesIO(plan.png)).convert("RGBA")
    layer = np.zeros((plan.height, plan.width, 4), dtype=np.uint8)
    for i, mask in enumerate(masks):
        r, g, b = (round(c * 255) for c in colorsys.hsv_to_rgb((i * 0.618) % 1, 0.8, 0.9))
        h, w = mask.bits.shape
        region = layer[mask.top:mask.top + h, mask.left:mask.left + w]
        bits = mask.bits[:region.shape[0], :region.shape[1]]
        region[bits] = (r, g, b, 110)
    image = Image.alpha_composite(base, Image.fromarray(layer, "RGBA"))
    draw = ImageDraw.Draw(image)
    for label in labels:
        draw.ellipse((label.x - 6, label.y - 6, label.x + 6, label.y + 6), fill=(220, 0, 0, 255))
        draw.text((label.x + 9, label.y - 7), label.name, fill=(220, 0, 0, 255))
    return image.convert("RGB")


def run_spike(client, plan_path: str | Path, out_root: str | Path) -> Path:
    plan = load_plan(plan_path)
    out = Path(out_root) / Path(plan_path).stem
    out.mkdir(parents=True, exist_ok=True)

    raw_rooms, reading = read_rooms(client, plan)
    (out / "rooms.json").write_text(raw_rooms, encoding="utf-8")

    concept_raw, concept_masks = segment(client, plan, "room")
    (out / "sam_concept.txt").write_text(concept_raw, encoding="utf-8")
    draw_overlay(plan, concept_masks, reading.rooms).save(out / "overlay_concept.png")

    point_masks: list[Mask] = []
    if reading.rooms:
        points_raw, point_masks = segment(client, plan, point_prompt(reading.rooms, plan.width, plan.height))
        (out / "sam_points.txt").write_text(points_raw, encoding="utf-8")
    draw_overlay(plan, point_masks, reading.rooms).save(out / "overlay_points.png")

    summary = {
        "plan": str(plan_path),
        "size": [plan.width, plan.height],
        "scale": reading.scale,
        "labels": len(reading.rooms),
        "concept_masks": len(concept_masks),
        "point_masks": len(point_masks),
        "rooms": [asdict(room) for room in reading.rooms],
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plan", help="Plan PDF (first page) or image")
    parser.add_argument("--out", default=".data/spike", help="Output folder (git-ignored)")
    args = parser.parse_args()
    out = run_spike(make_client(), args.plan, args.out)
    print(json.dumps(json.loads((out / "summary.json").read_text(encoding="utf-8")), ensure_ascii=False, indent=2))
    print(f"Outputs in {out}")
