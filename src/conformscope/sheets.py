"""A dossier's sheets: one per page of the PDF an architect sends for a whole building.

A building comes as one PDF, floor plans mixed with a plan de masse, toitures, coupes, in
no set order. Each page is a **sheet**, named by the title the architect printed on it.
A **plan annexe** -- masse, situation, toiture(s), combles -- is listed but never checked,
and is decided by its title alone: a note elsewhere on a real floor plan ("+ accès
toiture") would drop it (pmr-checker, docs/adr/0020).

Reading the titles costs no model call, so a dossier answers at once; each sheet is
checked the first time it is opened.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pymupdf  # type: ignore[import-untyped]

# "PLAN N°" is the cartouche's label for the sheet number, not a title.
_NUMBER_LABEL = re.compile(r"^PLAN\s*N\s*(?:°|º|�|O\b|\.|$)")
# A dossier may hold several buildings: "BÂTIMENT A - Plan du niveau R+1".
_BUILDING = re.compile(r"^(B[AÂ]T(?:IMENT)?\.?\s+\w+)\s*[-–:]\s*", re.IGNORECASE)
_TITLE = re.compile(r"^(?:BAT(?:IMENT)?\.?\s+\w+\s*[-–:]\s*)?PLAN\b")
# The key plan placing the level in the building, an inset on most sheets.
_KEY_PLAN = re.compile(r"\bREPERAGE\b")
_ANNEXE = re.compile(r"\b(?:MASSE|SITUATION|TOITURES?|COMBLES?)\b")
_CONNECTIVE = re.compile(r"^(?:DU|DE LA|DES|DE|D')\s*", re.IGNORECASE)
# The printed scale a title often ends on: "R+1 - 1:50", "R+1_50", "RDC ech. 1/100".
_SCALE_SUFFIX = re.compile(r"(?:\s*[-–_]\s*|\s+(?:ECH\.?|ÉCH\.?|ECHELLE|ÉCHELLE)?\s*)(?:1\s*[:/]\s*)?(?:50|100|200)\s*$",
                           re.IGNORECASE)


@dataclass(frozen=True)
class Sheet:
    page: int
    title: str | None   # as printed, None when no title was found
    name: str           # what the sheet tabs show
    annexe: bool        # listed, never checked


def _folded(text: str) -> str:
    """Upper case, accents and the replacement glyphs of a mis-encoded font aside, so
    "Façade", "FACADE" and "FA�ADE" read alike."""
    plain = unicodedata.normalize("NFKD", text)
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", plain.upper()).strip()


def title_of(page: pymupdf.Page) -> str | None:
    """The largest line that begins "PLAN", the sheet-number label and the key plan aside.
    A note that happens to begin with the word is printed small and loses to the
    cartouche's title."""
    best: tuple[float, str] | None = None
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"]).strip()
            folded = _folded(text)
            if not _TITLE.match(folded) or _NUMBER_LABEL.match(folded) or _KEY_PLAN.search(folded):
                continue
            size = max(span["size"] for span in line["spans"])
            if best is None or size > best[0]:
                best = (size, text)
    return re.sub(r"\s+", " ", best[1]) if best else None


def is_annexe(title: str | None) -> bool:
    return title is not None and bool(_ANNEXE.search(_folded(title)))


def name_of(title: str | None, page: int) -> str:
    """"PLAN DU R+1" is "R+1"; an annexe keeps its whole title, in sentence case, since
    what it draws is its name; no title is "Page n"."""
    if title is None:
        return f"Page {page + 1}"
    if is_annexe(title):
        return title[:1].upper() + title[1:].lower()
    building = _BUILDING.match(title)
    rest = title[building.end():] if building else title
    rest = _CONNECTIVE.sub("", re.sub(r"(?i)^plan\b\s*", "", rest))
    rest = _SCALE_SUFFIX.sub("", rest).strip() or f"Page {page + 1}"
    if not building:
        return rest
    word, letter = building.group(1).split(maxsplit=1)
    return f"{word.capitalize()} {letter} · {rest}"


def read_sheets(path: str | Path) -> list[Sheet]:
    """Every page of a PDF as a sheet, in page order; a picture is one sheet."""
    path = Path(path)
    if path.suffix.lower() != ".pdf":
        return [Sheet(0, None, name_of(None, 0), False)]
    sheets = []
    # Opened from bytes: a PDF that fails to open leaves no handle on the file, which on
    # Windows would keep a refused upload's folder from being removed.
    with pymupdf.open(stream=path.read_bytes(), filetype="pdf") as doc:
        for i, page in enumerate(doc):
            try:
                title = title_of(page)
            except Exception:  # a page whose text will not extract has no title
                title = None
            sheets.append(Sheet(i, title, name_of(title, i), is_annexe(title)))
    return sheets
