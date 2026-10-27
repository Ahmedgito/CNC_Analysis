"""General notes: the numbered block under a NOTES heading.

Notes carry information the title block often does not: the unit declaration ("ALL DIMENSIONS
IN MM"), the general tolerance, sometimes the material ("MATERIAL: MILD STEEL, IS 2062 E250"),
heat treatment and finish. Each note becomes one fact with its number as key, and is tagged with
the field it states so the cross-check and the title-block pointers can find it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.ingestion.pdf.layout import PageText, Segment, Table

_HEADING_RE = re.compile(r"^(GENERAL\s+)?NOTES?\s*:?$", re.IGNORECASE)
_NUMBERED_RE = re.compile(r"^(?:NOTE\s*)?\(?(\d{1,2})\s*[.):]\s*(.+)$", re.IGNORECASE)
_LOOSE_NOTE_RE = re.compile(r"^NOTE\s*(\d{1,2})\s*[:.\-]\s*(.+)$", re.IGNORECASE)

# "DIMENSIONS IN MM": the "IN" there is a preposition, so explicit unit words are looked for first.
_UNITS_KEY_RE = re.compile(r"\b(?:ALL\s+)?(?:DIM(?:ENSION)?S?|UNITS?)\b([^.]*)", re.IGNORECASE)
_UNIT_WORD_RE = re.compile(r"\b(MM|MILLIMET(?:ER|RE)S?|INCH(?:ES)?)\b", re.IGNORECASE)
_BARE_IN_RE = re.compile(r"[:=]\s*IN\b|\bIN\s*$", re.IGNORECASE)
_TOLERANCE_RE = re.compile(r"\bTOL(?:ERANCE)?S?\b.*(?:±|\+/-|\+-|ISO\s*2768)", re.IGNORECASE)
_MATERIAL_RE = re.compile(r"^\s*MATERIAL\s*[:\-]", re.IGNORECASE)
_FINISH_RE = re.compile(r"\b(?:SURFACE\s+)?FINISH\b|\bRa\s*\d|\b\d+\s*RMS\b", re.IGNORECASE)
_HEAT_RE = re.compile(
    r"\b(NORMALI[SZ]E|HARDEN|TEMPER|ANNEAL|STRESS[\s-]RELIEVE|NITRID|CARBURI[SZ]|QUENCH)",
    re.IGNORECASE,
)
_SCALE_RE = re.compile(r"\b(?:DRAWN\s+AT|SCALE)\s*\d+\s*:\s*\d+", re.IGNORECASE)


@dataclass(slots=True)
class Note:
    page: int
    number: int
    text: str
    bbox: list[float]
    canonical: str | None = None
    parsed: dict = field(default_factory=dict)


def unit_word(text: str) -> str | None:
    t = text.strip().upper()
    if t.startswith(("MM", "MILLIMET")):
        return "mm"
    if t.startswith(("INCH", "IN")):
        return "in"
    return None


def declared_unit(text: str) -> str | None:
    """'ALL DIMENSIONS IN MM' -> mm; 'DIMENSIONS IN INCHES' -> in; 'UNITS: IN' -> in."""
    m = _UNITS_KEY_RE.search(text)
    if not m:
        return None
    tail = m.group(1)
    w = _UNIT_WORD_RE.search(tail)
    if w:
        return unit_word(w.group(1))
    return "in" if _BARE_IN_RE.search(tail) else None


def classify(text: str) -> tuple[str | None, dict]:
    """The field a note states, with any value it carries, in priority order."""
    u = declared_unit(text)
    if u:
        return "units", {"unit": u}
    if _MATERIAL_RE.search(text):
        return "material", {}
    if _TOLERANCE_RE.search(text):
        return "tolerance", {}
    if _HEAT_RE.search(text):
        return "heat_treatment", {}
    if _FINISH_RE.search(text):
        return "surface_finish", {}
    if _SCALE_RE.search(text):
        return "scale", {}
    return None, {}


def _bbox(segs: list[Segment]) -> list[float]:
    return [
        round(min(s.x0 for s in segs), 1),
        round(min(s.top for s in segs), 1),
        round(max(s.x1 for s in segs), 1),
        round(max(s.bottom for s in segs), 1),
    ]


def find_notes(page: PageText, exclude: list[Table]) -> tuple[list[Note], list[Segment]]:
    """Numbered notes on a page and the segments they consumed (so they are not re-read)."""
    segs = [s for s in page.segments if s.upright and not any(t.contains(s) for t in exclude)]
    notes: list[Note] = []
    used: list[Segment] = []
    headings = [s for s in segs if _HEADING_RE.match(s.text.strip())]
    for heading in headings:
        used.append(heading)
        block = sorted(
            (s for s in segs if s.top > heading.top and abs(s.x0 - heading.x0) <= 15),
            key=lambda s: s.top,
        )
        current: list[Segment] = []
        number: int | None = None
        last_bottom = heading.bottom
        line_h = heading.bottom - heading.top
        for s in block:
            if s.top - last_bottom > max(3 * line_h, 18):
                break
            m = _NUMBERED_RE.match(s.text.strip())
            if m:
                if number is not None and current:
                    notes.append(_note(page.number, number, current))
                number, current = int(m.group(1)), [s]
            elif number is not None:
                current.append(s)  # continuation line of the current note
            else:
                break
            used.append(s)
            last_bottom = s.bottom
        if number is not None and current:
            notes.append(_note(page.number, number, current))
    if not headings:
        for s in segs:
            m = _LOOSE_NOTE_RE.match(s.text.strip())
            if m:
                notes.append(_note(page.number, int(m.group(1)), [s], m.group(2)))
                used.append(s)
    seen: set[int] = set()
    unique = [n for n in notes if not (n.number in seen or seen.add(n.number))]  # type: ignore[func-returns-value]
    return unique, used


def _note(page: int, number: int, segs: list[Segment], text: str | None = None) -> Note:
    if text is None:
        first = _NUMBERED_RE.match(segs[0].text.strip())
        head = first.group(2) if first else segs[0].text
        text = " ".join([head, *(s.text for s in segs[1:])]).strip()
    canonical, parsed = classify(text)
    return Note(page, number, text, _bbox(segs), canonical, parsed)
