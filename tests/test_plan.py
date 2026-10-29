import io

import pymupdf
import pytest
from PIL import Image

from conformscope.plan import load_plan


def _png(path, size=(300, 200)):
    Image.new("RGB", size, "white").save(path)
    return path


def test_png_plan_keeps_its_size(tmp_path):
    plan = load_plan(_png(tmp_path / "plan.png"))

    assert (plan.width, plan.height) == (300, 200)
    assert Image.open(io.BytesIO(plan.png)).size == (300, 200)


def test_pdf_plan_renders_first_page_at_dpi(tmp_path):
    path = tmp_path / "plan.pdf"
    doc = pymupdf.open()
    doc.new_page(width=720, height=360)  # 10 x 5 inches
    doc.save(path)

    plan = load_plan(path, dpi=100)

    assert (plan.width, plan.height) == (1000, 500)


def test_large_plan_is_capped_on_its_long_side(tmp_path):
    plan = load_plan(_png(tmp_path / "big.png", (4000, 1000)), max_side=2000)

    assert (plan.width, plan.height) == (2000, 500)


def test_data_url_is_a_png(tmp_path):
    plan = load_plan(_png(tmp_path / "plan.png"))

    assert plan.data_url().startswith("data:image/png;base64,")


def test_unknown_file_type_is_rejected(tmp_path):
    path = tmp_path / "plan.docx"
    path.write_bytes(b"nope")

    with pytest.raises(ValueError, match="docx"):
        load_plan(path)
