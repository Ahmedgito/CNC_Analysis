"""Locate the header row of a sheet and describe its columns.

Job-card registers often have banner rows ("ACME ... JOB CARD REGISTER", "Issued: Oct 2026")
above the real header, and some sheets put units on a second header row. We score the first
rows by how header-like they are and keep everything above the header as banner context.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.ingestion.canonical import HeaderMatch, extract_unit, match_header
from app.ingestion.cells import RawCell, Sheet, column_letter

MAX_HEADER_SCAN_ROWS = 20
_UNIT_ROW_TOKENS = {
    "mm",
    "in",
    "inch",
    "min",
    "mins",
    "h",
    "hr",
    "hrs",
    "s",
    "sec",
    "µm",
    "um",
    "kg",
    "g",
    "lb",
    "pcs",
    "nos",
    "ea",
    "%",
}


@dataclass(frozen=True, slots=True)
class Column:
    col: int
    header: str
    match: HeaderMatch

    @property
    def letter(self) -> str:
        return column_letter(self.col)


@dataclass(slots=True)
class TableLayout:
    header_row: int
    columns: list[Column]
    banner: list[RawCell] = field(default_factory=list)
    unit_row: int | None = None

    @property
    def first_data_row(self) -> int:
        return (self.unit_row or self.header_row) + 1

    def column(self, col: int) -> Column | None:
        return next((c for c in self.columns if c.col == col), None)


def _is_unit_token(text: str) -> bool:
    return text.strip().strip("()[]").casefold() in _UNIT_ROW_TOKENS


def _row_score(cells: list[RawCell]) -> tuple[float, int]:
    if len(cells) < 2:
        return (float("-inf"), 0)
    text_cells = [c for c in cells if c.value_type == "text"]
    non_text = len(cells) - len(text_cells)
    hits = sum(1 for c in text_cells if match_header(c.display_text).canonical is not None)
    return (hits * 3 + len(text_cells) - non_text * 2, hits)


def detect_layout(sheet: Sheet) -> TableLayout | None:
    """Return the most header-like row in the first rows, or ``None`` for non-tabular sheets."""
    best_row, best_score, best_hits = 0, float("-inf"), 0
    for r in range(1, min(sheet.max_row, MAX_HEADER_SCAN_ROWS) + 1):
        score, hits = _row_score(sheet.row_cells(r))
        if score > best_score:
            best_row, best_score, best_hits = r, score, hits
    if best_row == 0:
        return None
    header_cells = sheet.row_cells(best_row)
    if best_hits == 0 and not all(c.value_type == "text" for c in header_cells):
        return None

    # Optional units row directly under the header ("mm", "min", ...).
    unit_row = None
    below = sheet.row_cells(best_row + 1)
    unit_hits = sum(_is_unit_token(c.display_text) for c in below)
    if (
        below
        and unit_hits >= max(1, len(below) // 2)
        and all(c.value_type == "text" for c in below)
    ):
        unit_row = best_row + 1
    units_by_col = {c.col: c.display_text.strip().strip("()[]") for c in below} if unit_row else {}

    # Every column that holds data gets a Column, even if its header is blank.
    data_cols = {
        col for (r, col), cell in sheet.cells.items() if r > best_row and not cell.is_empty
    }
    header_by_col = {c.col: c for c in header_cells}
    columns: list[Column] = []
    for col in sorted(data_cols | set(header_by_col)):
        cell = header_by_col.get(col)
        header = cell.display_text if cell else f"Column {column_letter(col)}"
        if col in units_by_col and extract_unit(header)[1] is None:
            header = f"{header} ({units_by_col[col]})"
        columns.append(Column(col=col, header=header, match=match_header(header)))

    banner = [c for (r, _), c in sorted(sheet.cells.items()) if r < best_row and not c.is_empty]
    return TableLayout(header_row=best_row, columns=columns, banner=banner, unit_row=unit_row)
