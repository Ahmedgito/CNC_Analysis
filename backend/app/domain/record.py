"""Part record: the single shape shared by ingestion, the LLM context, the verifier and the UI.

Every value carries a ``cell_id`` of the form ``<file stem>!<sheet>!<column><row>`` so any claim
can be traced to an exact spreadsheet cell (and a judge can open the file and check it).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

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


class ColumnInfo(BaseModel):
    col: str
    header: str
    canonical: str | None = None
    unit: str | None = None


class RecordRow(BaseModel):
    row: int
    cells: list[CellRef]


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


class SourceStatus(BaseModel):
    available: bool
    files: list[str] = Field(default_factory=list)
    note: str | None = None


class PartRecord(BaseModel):
    part_key: str
    display_part_number: str
    base_key: str
    suffix: str | None = None
    sources: dict[SourceKind, SourceStatus]
    sheets: list[SheetSlice]
    available_fields: list[str]
    warnings: list[str] = Field(default_factory=list)

    def iter_cells(self) -> list[CellRef]:
        out: list[CellRef] = []
        for s in self.sheets:
            out.extend(s.banner)
            for r in s.rows:
                out.extend(r.cells)
        return out

    def cell_index(self) -> dict[str, CellRef]:
        return {c.cell_id: c for c in self.iter_cells()}

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
