"""Raw cell model and text normalisation.

A ``RawCell`` is a faithful, reader-independent record of one spreadsheet cell. Nothing in
here interprets meaning; it only preserves what the file says so every later answer can be
traced back to an exact cell.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Literal

ValueType = Literal["number", "text", "date", "bool", "formula", "error", "empty"]
CellValue = str | int | float | bool | datetime | date | time | None

_WS_RE = re.compile(r"\s+")
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍﻿⁠"), None)
# Diameter look-alikes collapse to Ø; multiplication look-alikes to x (for matching only).
_DIAMETER_CHARS = str.maketrans({"⌀": "Ø", "∅": "Ø", "ø": "Ø"})
# Hyphen and minus look-alikes that NFKC leaves alone (models often emit U+2011 in "6061‑T6").
_DASH_CHARS = str.maketrans(dict.fromkeys("‐‑‒–—―−﹣－", "-"))
_ZERO_FMT_RE = re.compile(r"^0+$")


def column_letter(col: int) -> str:
    """1-based column index to Excel letters (1 -> A, 27 -> AA)."""
    letters = ""
    while col > 0:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def clean_text(value: str) -> str:
    """Display-safe cleanup: drop zero-width chars, turn NBSP into space, trim ends.

    Characters that carry engineering meaning (Ø, ±, µ, ×) are preserved exactly.
    """
    return value.translate(_ZERO_WIDTH).replace(" ", " ").strip()


def normalize_for_match(value: str) -> str:
    """Aggressive normalisation used only for comparisons (never for display).

    NFKC folds compatibility forms (micro sign to mu, full-width digits); diameter symbols
    are unified; whitespace is collapsed; case is folded.
    """
    text = unicodedata.normalize("NFKC", clean_text(value)).translate(_DIAMETER_CHARS)
    text = text.translate(_DASH_CHARS)
    text = text.replace("×", "x")
    return _WS_RE.sub(" ", text).strip().casefold()


def format_number(value: int | float, number_format: str | None = None) -> str:
    """Render a numeric cell the way a person reading the sheet would see it."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, int) and number_format and _ZERO_FMT_RE.match(number_format):
        return str(value).zfill(len(number_format))
    if isinstance(value, float):
        return repr(value)
    return str(value)


@dataclass(frozen=True, slots=True)
class RawCell:
    sheet: str
    row: int  # 1-based
    col: int  # 1-based
    value: CellValue
    value_type: ValueType
    number_format: str | None = None
    formula: str | None = None
    hidden: bool = False
    comment: str | None = None
    merged_from: str | None = None  # top-left coordinate when the value was filled from a merge

    @property
    def col_letter(self) -> str:
        return column_letter(self.col)

    @property
    def coordinate(self) -> str:
        return f"{self.col_letter}{self.row}"

    @property
    def display_text(self) -> str:
        """Human-faithful text of the cell, used for display, prompts and verification."""
        v = self.value
        if v is None:
            return ""
        if isinstance(v, bool):
            return "TRUE" if v else "FALSE"
        if isinstance(v, int | float):
            return format_number(v, self.number_format)
        if isinstance(v, datetime):
            return v.date().isoformat() if v.time() == time(0) else v.isoformat(sep=" ")
        if isinstance(v, date | time):
            return v.isoformat()
        return clean_text(str(v))

    @property
    def is_empty(self) -> bool:
        return self.display_text == ""


@dataclass(slots=True)
class Sheet:
    name: str
    state: Literal["visible", "hidden", "veryHidden"] = "visible"
    cells: dict[tuple[int, int], RawCell] = field(default_factory=dict)

    @property
    def max_row(self) -> int:
        return max((r for r, _ in self.cells), default=0)

    @property
    def max_col(self) -> int:
        return max((c for _, c in self.cells), default=0)

    def get(self, row: int, col: int) -> RawCell | None:
        return self.cells.get((row, col))

    def row_cells(self, row: int) -> list[RawCell]:
        return [c for (r, _), c in sorted(self.cells.items()) if r == row and not c.is_empty]


@dataclass(slots=True)
class Workbook:
    file_name: str
    sheets: list[Sheet]
    file_format: Literal["xlsx", "xls", "csv"]
    warnings: list[str] = field(default_factory=list)

    @property
    def file_stem(self) -> str:
        return self.file_name.rsplit(".", 1)[0]
