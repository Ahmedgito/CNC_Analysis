"""Part record: the single shape shared by ingestion, the LLM context, the verifier and the UI.

A record combines one part's spreadsheet rows (``sheets``) and drawings (``drawings``). Every value
has a fact id (``<file stem>!<sheet>!<column><row>`` for a cell, ``<file stem>!p<page>!...`` for a
drawing), so any claim can be traced to an exact place in a file a judge can open.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.domain.drawing import REGION_LABEL, CrossCheck, DrawingSlice
from app.domain.evidence import Fact

SheetKind = Literal["attributes", "rows"]
SourceKind = Literal["excel", "pdf", "iges"]


def make_cell_id(file_stem: str, sheet: str, col_letter: str, row: int) -> str:
    return f"{file_stem}!{sheet}!{col_letter}{row}"


class CellRef(BaseModel):
    cell_id: str
    file: str
    sheet: str
    row: int
    col: str
    header: str
    canonical: str | None = None
    unit: str | None = None
    value: str  # display text, exactly as a person reads it in Excel
    value_type: str
    hidden: bool = False
    comment: str | None = None
    formula: str | None = None

    def to_fact(self, group: str, stale: bool = False, stale_reason: str | None = None) -> Fact:
        return Fact(
            fact_id=self.cell_id,
            source="excel",
            file=self.file,
            locator=f"{self.sheet} › {self.col}{self.row}",
            label=self.header,
            canonical=self.canonical,
            value=self.value,
            unit=self.unit,
            stale=stale,
            stale_reason=stale_reason,
            hidden=self.hidden,
            group=group,
            sheet=self.sheet,
            row=self.row,
            col=self.col,
        )


class ColumnInfo(BaseModel):
    col: str
    header: str
    canonical: str | None = None
    unit: str | None = None


class RecordRow(BaseModel):
    row: int
    cells: list[CellRef]
    stale: bool = False  # superseded revision, obsolete status
    stale_reason: str | None = None


class SheetSlice(BaseModel):
    """The rows of one sheet that belong to one part."""

    file: str
    sheet: str
    kind: SheetKind
    header_row: int
    hidden: bool = False
    columns: list[ColumnInfo]
    rows: list[RecordRow]
    banner: list[CellRef] = Field(default_factory=list)
    stale: bool = False  # an archive / obsolete / history sheet
    stale_reason: str | None = None
    layout: str = "table"  # table | card (a vertical label/value part card)
    default_unit: str | None = None  # from a banner statement such as "Units: mm unless stated"


class SourceStatus(BaseModel):
    available: bool
    files: list[str] = Field(default_factory=list)
    note: str | None = None
    readable: bool | None = None  # pdf: False when every drawing is a scan not yet read
    scanned: list[str] = Field(default_factory=list)  # pdf: files that are image-only scans
    current_revision: str | None = None


class PartRecord(BaseModel):
    part_key: str
    display_part_number: str
    base_key: str
    suffix: str | None = None
    sources: dict[SourceKind, SourceStatus]
    sheets: list[SheetSlice]
    available_fields: list[str]
    warnings: list[str] = Field(default_factory=list)
    drawings: list[DrawingSlice] = Field(default_factory=list)
    cross_checks: list[CrossCheck] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)  # other part numbers seen for this part

    def iter_cells(self) -> list[CellRef]:
        out: list[CellRef] = []
        for s in self.sheets:
            out.extend(s.banner)
            for r in s.rows:
                out.extend(r.cells)
        return out

    def cell_index(self) -> dict[str, CellRef]:
        return {c.cell_id: c for c in self.iter_cells()}

    def facts(self) -> list[Fact]:
        """Every citable fact in the record, spreadsheet first, then drawings."""
        out: list[Fact] = []
        for s in self.sheets:
            for b in s.banner:
                out.append(b.to_fact(group=f"{b.file}!{s.sheet}!banner"))
            for r in s.rows:
                stale = s.stale or r.stale
                reason = s.stale_reason if s.stale else r.stale_reason
                group = f"{s.file}!{s.sheet}!r{r.row}"
                out.extend(c.to_fact(group, stale, reason) for c in r.cells)
        for d in self.drawings:
            for f in d.facts:
                bbox = f.bboxes[0] if f.bboxes else None
                out.append(
                    Fact(
                        fact_id=f.fact_id,
                        source="pdf",
                        file=d.file,
                        locator=f"p{f.page} › {REGION_LABEL[f.region]} › {f.label}",
                        label=f.label,
                        canonical=f.canonical,
                        value=f.value,
                        unit=f.unit,
                        confidence=f.confidence,
                        stale=f.stale,
                        stale_reason=f.stale_reason,
                        group=f"{d.file}!p{f.page}!{f.region}",
                        page=f.page,
                        region=f.region,
                        kind=f.kind,
                        bbox=bbox,
                    )
                )
        return out

    def fact_index(self) -> dict[str, Fact]:
        return {f.fact_id: f for f in self.facts()}

    def unread_scans(self) -> list[str]:
        return [d.file for d in self.drawings if d.scanned and d.extraction == "none"]

    def description(self) -> str | None:
        for c in self.iter_cells():
            if c.canonical == "description" and c.value:
                return c.value
        return None


class PartSummary(BaseModel):
    part_key: str
    display_part_number: str
    description: str | None
    sources: dict[SourceKind, SourceStatus]
    files: list[str]
