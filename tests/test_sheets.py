import pymupdf
import pytest

from conformscope.sheets import is_annexe, name_of, read_sheets, title_of


def _page(doc, *lines, width=842, height=595):
    """A page carrying each (text, fontsize) line, top to bottom."""
    page = doc.new_page(width=width, height=height)
    for i, (text, size) in enumerate(lines):
        page.insert_text((40, 60 + 40 * i), text, fontsize=size)
    return page


def test_the_title_is_the_largest_line_beginning_plan():
    doc = pymupdf.open()
    page = _page(doc, ("Plan cuisiniste impossible", 8), ("PLAN DU R+1", 24), ("PLAN N° 4", 30))

    assert title_of(page) == "PLAN DU R+1"


def test_the_key_plan_inset_is_not_the_title():
    # Real sheets carry a small "plan de repérage" placing the level in the building,
    # often printed larger than the level's own title.
    doc = pymupdf.open()
    page = _page(doc, ("PLAN DU NIVEAU R+1", 18), ("PLAN DE REPÉRAGE", 26))

    assert title_of(page) == "PLAN DU NIVEAU R+1"


def test_a_title_may_name_its_building_first():
    doc = pymupdf.open()

    assert title_of(_page(doc, ("BATIMENT A - Plan du niveau R+1", 24))) == "BATIMENT A - Plan du niveau R+1"


def test_a_page_with_no_plan_line_has_no_title():
    doc = pymupdf.open()

    assert title_of(_page(doc, ("COUPE AA", 24))) is None


@pytest.mark.parametrize("title, annexe", [
    ("PLAN DE MASSE - GÉNÉRAL", True),
    ("Plan de situation", True),
    ("PLAN DES TOITURES", True),
    ("PLAN DES COMBLES", True),
    ("PLAN DU R+1", False),
    ("PLAN REZ DE CHAUSSÉE GÉNÉRAL", False),
    (None, False),
])
def test_a_plan_annexe_is_decided_by_its_title(title, annexe):
    assert is_annexe(title) is annexe


@pytest.mark.parametrize("title, name", [
    ("PLAN DU R+1", "R+1"),
    ("PLAN DU NIVEAU RDC", "NIVEAU RDC"),
    ("PLAN DE R+3 & R+4", "R+3 & R+4"),
    ("PLAN DE MASSE", "Plan de masse"),
    ("PLAN DE R+1 - 1:50", "R+1"),
    ("PLAN R+1_50", "R+1"),
    ("BÂTIMENT A - Plan du niveau R+1", "Bâtiment A · niveau R+1"),
])
def test_a_sheet_is_named_from_its_title(title, name):
    assert name_of(title, page=0) == name


def test_a_sheet_with_no_title_is_named_by_its_page():
    assert name_of(None, page=2) == "Page 3"


def test_every_page_of_a_pdf_is_a_sheet_in_page_order(tmp_path):
    path = tmp_path / "dossier.pdf"
    doc = pymupdf.open()
    _page(doc, ("PLAN DE MASSE", 24))
    _page(doc, ("PLAN DU RDC", 24))
    _page(doc, ("coupe", 12), width=595, height=842)
    doc.save(path)

    sheets = read_sheets(path)

    assert [(s.page, s.name, s.annexe) for s in sheets] == [
        (0, "Plan de masse", True), (1, "RDC", False), (2, "Page 3", False)]


def test_a_picture_is_one_sheet(tmp_path):
    path = tmp_path / "plan.png"
    path.write_bytes(b"\x89PNG")

    (sheet,) = read_sheets(path)

    assert (sheet.page, sheet.title, sheet.name, sheet.annexe) == (0, None, "Page 1", False)
