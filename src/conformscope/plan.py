"""A plan as the models see it: one PNG page and its pixel size."""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from PIL import Image

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


@dataclass(frozen=True)
class Plan:
    png: bytes
    width: int
    height: int

    def data_url(self) -> str:
        return "data:image/png;base64," + base64.b64encode(self.png).decode("ascii")


def load_plan(path: str | Path, dpi: int = 150, max_side: int = 2000) -> Plan:
    """Render the first page of a PDF, or read an image, as a PNG no longer than max_side."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        with pymupdf.open(path) as doc:
            pix = doc[0].get_pixmap(dpi=dpi)
            image = Image.open(io.BytesIO(pix.tobytes("png")))
    elif suffix in IMAGE_SUFFIXES:
        image = Image.open(path)
    else:
        raise ValueError(f"Unsupported plan file type: {suffix or path.name}")

    image = image.convert("RGB")
    if max(image.size) > max_side:
        ratio = max_side / max(image.size)
        image = image.resize((round(image.width * ratio), round(image.height * ratio)))

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return Plan(png=buffer.getvalue(), width=image.width, height=image.height)
