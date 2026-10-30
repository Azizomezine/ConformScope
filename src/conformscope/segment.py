"""Room masks from SAM 3.1 on the Meta Model API."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from meta_sam_parser import (
    CompletedOutcome,
    FramePrompt,
    PromptBox,
    PromptObject,
    PromptPoint,
    build_object_prompt,
    decode_mask_to_raster,
    image_segmentation_format,
)

from conformscope.labels import FixtureBox, RoomLabel
from conformscope.plan import Plan

MODEL = "sam-3.1"


@dataclass(frozen=True)
class Mask:
    object_id: str
    left: int
    top: int
    bits: np.ndarray  # bool, shape (height, width), placed at (left, top) on the plan


def parse_segmentation(output_text: str) -> list[Mask]:
    parser = image_segmentation_format().create_parser()
    parser.push(output_text)
    result = parser.finish(CompletedOutcome()).result
    masks = []
    for record in result.records:
        if record.kind != "mask":
            continue
        raster = decode_mask_to_raster(record.mask)
        bits = np.frombuffer(raster, dtype=np.uint8).reshape(record.mask.height, record.mask.width)
        masks.append(Mask(record.object_id, record.bounds.left, record.bounds.top, bits.astype(bool)))
    return masks


def point_prompt(labels: list[RoomLabel], width: int, height: int) -> str:
    """One SAM object per room label, prompted with a positive point on the label."""
    objects = [
        PromptObject(id=i, prompts=[FramePrompt(points=[PromptPoint(label.x, label.y)])])
        for i, label in enumerate(labels)
    ]
    return build_object_prompt(size=(width, height), objects=objects)


def box_prompt(boxes: list[FixtureBox], width: int, height: int) -> str:
    """One SAM object per fixture, prompted with the box Muse Spark drew round it."""
    objects = [
        PromptObject(id=i, prompts=[FramePrompt(box=PromptBox(b.x1, b.y1, b.x2 + 1, b.y2 + 1))])
        for i, b in enumerate(boxes)
    ]
    return build_object_prompt(size=(width, height), objects=objects)


def segment(client, plan: Plan, prompt: str) -> tuple[str, list[Mask]]:
    """Send a concept phrase or an object prompt to SAM 3.1; return the raw output and masks."""
    response = client.responses.create(
        model=MODEL,
        input=[{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": plan.data_url()},
        ]}],
        metadata={"mask_encoding": "one_bit", "include_confidence": "true"},
    )
    text = response.output_text or ""
    return text, parse_segmentation(text)
