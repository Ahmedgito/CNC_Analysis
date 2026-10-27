"""Title block: the label/value table in a drawing's corner.

Vocabulary-driven rather than position-driven, because title blocks move (bottom-right on most
sheets, top-right on 2281) and relabel themselves (PART NO / DWG NO, MATERIAL / MATL, UNITS /
UNIT). A ruled two-column table with at least three recognised labels is the title block; when a
drawing has no ruled table, label/value pairs on shared baselines are used instead.

Compound cells ("DRAWN / REV" = "SK / A", "SHEET / REV" = "1 of 1 / B") are split into one fact
per label. A value of "SEE NOTE 3" is kept verbatim and linked to the note it points to.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.ingestion.pdf.layout import PageText, Segment, Table

# key -> (canonical field or None, labels as printed)
_FIELDS: dict[str, tuple[str | None, tuple[str, ...]]] = {
    "part_number": (
        "part_number",
        (
            "PART NO",
            "PART NUMBER",
            "PART #",
            "P/N",
            "PN",
            "DWG NO",
            "DRAWING NO",
            "DRAWING NUMBER",
            "DRG NO",
            "DOC NO",
            "ITEM NO",
        ),
    ),
    "title": ("description", ("PART NAME", "TITLE", "DESCRIPTION", "NAME", "PART DESCRIPTION")),
    "material": ("material", ("MATERIAL", "MATL", "MAT'L", "MAT", "MATERIAL SPEC")),
    "scale": ("scale", ("SCALE",)),
    "units": ("units", ("UNITS", "UNIT", "DIMENSIONS IN", "DIMS IN", "DIMS")),
    "general_tolerance": (
        "tolerance",
        ("GEN TOLERANCE", "GENERAL TOLERANCE", "GEN TOL", "TOLERANCE", "TOL", "TOLERANCES"),
    ),
    "surface_finish": (
        "surface_finish",
        ("SURFACE FINISH", "FINISH", "SURF FINISH", "SURFACE ROUGHNESS", "ROUGHNESS"),
    ),
    "revision": ("revision", ("REV", "REVISION", "ISSUE", "REV LEVEL")),
    "sheet": ("sheet", ("SHEET", "SHT", "SHEET NO")),
    "drawn_by": ("drawn_by", ("DRAWN", "DRAWN BY", "DRN", "DESIGNED BY", "DESIGNER")),
    "checked_by": ("checked_by", ("CHECKED", "CHECKED BY", "CHK")),
    "approved_by": ("approved_by", ("APPROVED", "APPROVED BY", "APPD")),
    "date": ("date", ("DATE", "DRAWN DATE", "ISSUE DATE")),
    "weight": ("weight", ("WEIGHT", "MASS", "WT")),
    "heat_treatment": ("heat_treatment", ("HEAT TREATMENT", "HEAT TREAT", "H/T", "HT")),
    "treatment": ("treatment", ("TREATMENT", "COATING", "PLATING", "PROTECTION")),
    "projection": ("projection", ("PROJECTION", "ANGLE OF PROJECTION")),
}
_LABEL_TO_KEY = {label: key for key, (_, labels) in _FIELDS.items() for label in labels}
_POINTER_RE = re.compile(r"\bSEE\s+NOTE\s*(\d{1,2})\b", re.IGNORECASE)
_MIN_LABELS = 3


def canonical_for(key: str) -> str | None:
    return _FIELDS.get(key, (None, ()))[0]


def _norm_label(text: str) -> str:
    t = text.upper().replace(".", " ").replace(":", " ")
    t = re.sub(r"\s*/\s*", "/", t)
    return re.sub(r"\s+", " ", t).strip()


def _keys_for(label: str) -> list[str] | None:
    """Field keys for a printed label; compound labels ('DRAWN / REV') give several."""
    norm = _norm_label(label)
    if norm in _LABEL_TO_KEY:
        return [_LABEL_TO_KEY[norm]]
    parts = [p.strip() for p in norm.split("/") if p.strip()]
    if len(parts) > 1 and norm not in ("P/N", "H/T"):
        keys = [_LABEL_TO_KEY.get(p) for p in parts]
        if all(keys):
            return keys  # type: ignore[return-value]
    return None


@dataclass(slots=True)
class TitleField:
    key: str
    canonical: str | None
    label: str  # as printed, e.g. "DRAWN / REV"
    value: str  # the value part for this key, e.g. "A"
    bbox: list[float]
    pointer_note: int | None = None


@dataclass(slots=True)
class TitleBlock:
    page: int
    bbox: list[float]
    fields: list[TitleField]
    company: str | None = None

    def get(self, key: str) -> TitleField | None:
        return next((f for f in self.fields if f.key == key), None)


def _split_compound(keys: list[str], label: str, value: str, bbox: list[float]) -> list[TitleField]:
    if len(keys) == 1:
        return [TitleField(keys[0], canonical_for(keys[0]), label, value, bbox)]
    values = [v.strip() for v in value.split("/")]
    if len(values) != len(keys):
        return [TitleField(keys[0], canonical_for(keys[0]), label, value, bbox)]
    return [
        TitleField(k, canonical_for(k), f"{label} ({k.replace('_', ' ')})", v, bbox)
        for k, v in zip(keys, values, strict=True)
    ]


def _from_table(table: Table, page: int) -> TitleBlock | None:
    fields: list[TitleField] = []
    company: str | None = None
    recognised = 0
    for row in table.rows:
        cells = [c for c in row if c is not None]
        if not cells:
            continue
        if len(cells) == 1 or not cells[1].text:
            if company is None and cells[0].text and _keys_for(cells[0].text) is None:
                company = cells[0].text
            continue
        label_cell, value_cell = cells[0], cells[1]
        keys = _keys_for(label_cell.text)
        if keys is None or not value_cell.text:
            continue
        recognised += 1
        fields.extend(_split_compound(keys, label_cell.text, value_cell.text, value_cell.bbox))
    if recognised < _MIN_LABELS:
        return None
    return TitleBlock(page=page, bbox=table.bbox, fields=_dedupe(fields), company=company)


def _from_lines(page: PageText) -> TitleBlock | None:
    """No ruled table: pair a label segment with the next segment on the same baseline."""
    segs = [s for s in page.segments if s.upright]
    fields: list[TitleField] = []
    used: list[Segment] = []
    for s in segs:
        keys = _keys_for(s.text)
        if keys is None:
            continue
        right = [
            o for o in segs if o is not s and abs(o.top - s.top) <= 3 and 0 < o.x0 - s.x1 <= 250
        ]
        if not right:
            continue
        value = min(right, key=lambda o: o.x0)
        if _keys_for(value.text) is not None:
            continue
        fields.extend(_split_compound(keys, s.text, value.text, value.bbox))
        used.extend([s, value])
    if len({f.key for f in fields}) < _MIN_LABELS:
        return None
    x0 = min(u.x0 for u in used)
    top = min(u.top for u in used)
    x1 = max(u.x1 for u in used)
    bottom = max(u.bottom for u in used)
    return TitleBlock(page=page.number, bbox=[x0, top, x1, bottom], fields=_dedupe(fields))


def _dedupe(fields: list[TitleField]) -> list[TitleField]:
    seen: set[str] = set()
    out: list[TitleField] = []
    for f in fields:
        if f.key in seen:
            continue
        seen.add(f.key)
        m = _POINTER_RE.search(f.value)
        if m:
            f.pointer_note = int(m.group(1))
        out.append(f)
    return out


def find_title_block(page: PageText) -> TitleBlock | None:
    candidates = [tb for t in page.tables if (tb := _from_table(t, page.number))]
    if candidates:
        return max(candidates, key=lambda tb: len(tb.fields))
    return _from_lines(page)
