"""``Fact``: one citable statement from any source file, the unit every answer is built from.

Excel cells and PDF drawing facts are stored in their own shapes (``CellRef``, ``DrawingFact``)
because they carry different provenance. Everything downstream of storage (the prompt, the
verifier, the compute engine, the cross-check and the API) reads them through this one type, so
adding a source (IGES in Level 3) means writing one adapter to ``Fact``, not touching the
answer pipeline.

Fact id grammar, always ``<file stem>!...`` so an id names its file:

- Excel: ``<stem>!<sheet>!<col><row>``             e.g. ``mfg_record_A!Parts!C2``
- PDF:   ``<stem>!p<page>!<region>!<key>``          e.g. ``2283_bushing!p1!tb!material``
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

FactSource = Literal["excel", "pdf"]
# exact: the text is in the file verbatim. inferred: derived by a rule from text in the file
# (a "SEE NOTE 3" pointer, an unlabelled dimension). vision: read from a scanned image by a
# vision model, never verifiable against the file's text.
Confidence = Literal["exact", "inferred", "vision"]


class Fact(BaseModel):
    fact_id: str
    source: FactSource
    file: str
    locator: str  # human-readable position: "Parts › C2" or "p1 › Title block › Material"
    label: str  # header or drawing label exactly as printed
    canonical: str | None = None
    value: str  # verbatim text, as a person reads it in the file
    unit: str | None = None
    confidence: Confidence = "exact"
    stale: bool = False  # archived sheet, superseded revision, revision-history page
    stale_reason: str | None = None
    hidden: bool = False
    group: str  # facts read together: one spreadsheet row, one drawing region on one page

    # Excel provenance
    sheet: str | None = None
    row: int | None = None
    col: str | None = None

    # PDF provenance (bbox in PDF points, top-left origin, display orientation)
    page: int | None = None
    region: str | None = None
    kind: str | None = None
    bbox: list[float] | None = None

    @property
    def coordinate(self) -> str | None:
        return f"{self.col}{self.row}" if self.col and self.row else None
