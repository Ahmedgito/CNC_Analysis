"""PDF engineering drawings as stored in a part record, plus the cross-check between sources.

A ``DrawingSlice`` is one drawing file's contribution to a part: its pages, the facts read from
them, and what could not be read. ``CrossCheck`` rows compare the same field across the
spreadsheet, the drawing and the 3D model after unit reconciliation; they are computed
deterministically when the record is built, never by the language model.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain.evidence import Confidence

Region = Literal["title_block", "note", "dimension", "revision", "text"]
PageRole = Literal["drawing", "revision_history", "text", "scanned", "blank"]
Extraction = Literal["text", "vision", "none"]

REGION_CODE: dict[str, str] = {
    "title_block": "tb",
    "note": "note",
    "dimension": "dim",
    "revision": "rev",
    "text": "text",
}
REGION_LABEL: dict[str, str] = {
    "title_block": "Title block",
    "note": "Note",
    "dimension": "Dimension",
    "revision": "Revision history",
    "text": "Text",
}


def make_drawing_fact_id(file_stem: str, page: int, region: str, key: str) -> str:
    return f"{file_stem}!p{page}!{REGION_CODE[region]}!{key}"


class DrawingFact(BaseModel):
    fact_id: str
    page: int
    region: Region
    key: str  # title-block field, note number, dimension ordinal, revision letter
    kind: str | None = None  # dimension kind: diameter, bore, hole_pattern, thickness, ...
    label: str  # as printed: "MATL", "Note 3", "Ø48"
    canonical: str | None = None
    value: str
    unit: str | None = None
    confidence: Confidence = "exact"
    stale: bool = False
    stale_reason: str | None = None
    bboxes: list[list[float]] = Field(default_factory=list)  # one per occurrence on the page
    points_to: str | None = None  # "SEE NOTE 3" -> the note's fact id
    parsed: dict[str, Any] = Field(default_factory=dict)  # numbers read from the value


class DrawingPage(BaseModel):
    page: int
    width: float
    height: float
    rotation: int = 0  # the page's own /Rotate
    correction: int = 0  # extra clockwise turn applied so text reads upright; the viewer uses it
    role: PageRole
    char_count: int = 0
    image_count: int = 0
    units: str | None = None  # mm | in, from this page's title block or notes


class DrawingSlice(BaseModel):
    file: str
    file_stem: str
    sha256: str
    page_count: int
    pages: list[DrawingPage]
    facts: list[DrawingFact] = Field(default_factory=list)
    part_number: str | None = None  # as printed
    part_number_source: Literal["title_block", "text", "filename"] | None = None
    title: str | None = None
    current_revision: str | None = None
    units: str | None = None
    readable: bool = True  # False when no page has a text layer (a scan)
    scanned: bool = False
    extraction: Extraction = "text"
    warnings: list[str] = Field(default_factory=list)


Verdict = Literal[
    "agree",
    "agree_after_conversion",
    "equivalent_by_convention",
    "within_tolerance",  # differs by more than modelling precision but inside the stated tolerance
    "consistent",  # the part fits in the stated raw stock
    "not_modelled",  # the drawing calls for a feature models often leave out (chamfers)
    "disagree",
    "excel_only",
    "pdf_only",
    "iges_only",
    "not_comparable",
]
Source = Literal["excel", "pdf", "iges"]
PairKey = Literal["excel~pdf", "excel~iges", "pdf~iges"]


class CheckSide(BaseModel):
    """What one source says about the field."""

    source: Source
    facts: list[str] = Field(default_factory=list)
    value: str | None = None  # as written, or as measured
    normalised: str | None = None  # "50 mm", "6 × Ø10 mm"
    note: str | None = None  # how a unit was established, or why the source says nothing


class CrossCheck(BaseModel):
    """One field compared across the spreadsheet, the drawing and the 3D model.

    ``excel`` / ``pdf`` / ``excel_value`` / ``pdf_value`` are the Level 2 two-source fields and
    stay filled, so stored records and older clients keep working; ``sides`` and ``pairs`` carry
    the full comparison.
    """

    field: str  # material | outer_diameter | bore | holes | thickness | length | tolerance | ...
    label: str  # human name of the field
    verdict: Verdict  # the worst pairwise verdict
    excel: list[str] = Field(default_factory=list)  # fact ids on the spreadsheet side
    pdf: list[str] = Field(default_factory=list)  # fact ids on the drawing side
    iges: list[str] = Field(default_factory=list)  # fact ids on the model side
    excel_value: str | None = None
    pdf_value: str | None = None
    iges_value: str | None = None
    sides: list[CheckSide] = Field(default_factory=list)
    pairs: dict[str, Verdict] = Field(default_factory=dict)  # "excel~pdf" -> verdict
    odd_one_out: Source | None = None  # two sources agree, this one differs
    dissent: list[str] = Field(default_factory=list)  # fact ids of statements that differ
    detail: str  # one sentence a person can read: values, units, conversion, why
