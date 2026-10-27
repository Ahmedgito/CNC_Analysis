"""File readers: turn .xlsx / .xls / .csv into the reader-independent ``Workbook`` model.

Format is detected from magic bytes, not the extension, because exported files are often
misnamed. Each reader preserves cell types (a text "2282" stays text, a numeric 2280 stays a
number), number formats, formulas with their cached values, hidden state and comments.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, time
from pathlib import Path
from typing import Literal

from app.ingestion.cells import RawCell, Sheet, ValueType, Workbook

FileFormat = Literal["xlsx", "xls", "csv", "pdf"]

_ZIP_MAGIC = b"PK\x03\x04"
_OLE_MAGIC = b"\xd0\xcf\x11\xe0"
SUPPORTED_SUFFIXES = {".xlsx", ".xlsm", ".xls", ".csv", ".pdf"}
_PDF_MAGIC = b"%PDF-"
_CSV_NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?$")
_SCALAR_TYPES = (str, int, float, bool, datetime, date, time)


class UnsupportedFileError(ValueError):
    """Raised when a file is not a spreadsheet we can read."""


def sniff_format(data: bytes, file_name: str) -> FileFormat:
    # The PDF header may follow up to 1 KB of junk; it must be checked before the text heuristic,
    # which would otherwise take a PDF for a CSV file.
    if _PDF_MAGIC in data[:1024]:
        return "pdf"
    if file_name.lower().endswith(".pdf"):
        raise UnsupportedFileError(f"{file_name}: named .pdf but the content is not a PDF")
    if data.startswith(_ZIP_MAGIC):
        return "xlsx"
    if data.startswith(_OLE_MAGIC):
        return "xls"
    if file_name.lower().endswith((".csv", ".txt")) or _looks_like_text(data):
        return "csv"
    raise UnsupportedFileError(f"{file_name}: not an xlsx, xls or csv file")


def _looks_like_text(data: bytes) -> bool:
    head = data[:4096]
    if b"\x00" in head:
        return False
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def read_workbook(path: Path | str) -> Workbook:
    path = Path(path)
    return read_workbook_bytes(path.read_bytes(), path.name)


def read_workbook_bytes(data: bytes, file_name: str) -> Workbook:
    fmt = sniff_format(data, file_name)
    if fmt == "pdf":
        raise UnsupportedFileError(f"{file_name} is a PDF drawing, not a workbook")
    if fmt == "xlsx":
        return _read_xlsx(data, file_name)
    if fmt == "xls":
        return _read_xls(data, file_name)
    return _read_csv(data, file_name)


# --------------------------------------------------------------------------------------- xlsx


def _read_xlsx(data: bytes, file_name: str) -> Workbook:
    import openpyxl
    from openpyxl.cell.cell import MergedCell

    # Two loads: formulas/types from the first, Excel's last cached results from the second.
    wb_f = openpyxl.load_workbook(io.BytesIO(data), data_only=False)
    wb_v = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    warnings: list[str] = []
    sheets: list[Sheet] = []
    try:
        for ws in wb_f.worksheets:
            ws_v = wb_v[ws.title]
            state = ws.sheet_state if ws.sheet_state in ("hidden", "veryHidden") else "visible"
            sheet = Sheet(name=ws.title, state=state)  # type: ignore[arg-type]
            if state != "visible":
                warnings.append(f"{file_name} › {ws.title}: sheet is {state}; read and tagged")
            hidden_rows = {i for i, d in ws.row_dimensions.items() if d.hidden}
            hidden_cols = {k for k, d in ws.column_dimensions.items() if d.hidden}
            formulas_without_cache = 0

            for row in ws.iter_rows():
                for cell in row:
                    if isinstance(cell, MergedCell) or cell.value is None:
                        continue
                    value = cell.value
                    vtype: ValueType
                    formula = None
                    if cell.data_type == "f":
                        formula = str(value)
                        value = ws_v[cell.coordinate].value
                        vtype = "formula"
                        if value is None:
                            formulas_without_cache += 1
                    elif cell.data_type == "e":
                        vtype = "error"
                    elif cell.data_type == "b":
                        vtype = "bool"
                    elif cell.is_date:
                        vtype = "date"
                    elif isinstance(value, int | float):
                        vtype = "number"
                    else:
                        vtype = "text"
                    if not isinstance(value, _SCALAR_TYPES):
                        value = str(value)  # array formulas, rich text and other exotic objects
                    sheet.cells[(cell.row, cell.column)] = RawCell(
                        sheet=ws.title,
                        row=cell.row,
                        col=cell.column,
                        value=value,
                        value_type=vtype,
                        number_format=cell.number_format,
                        formula=formula,
                        hidden=state != "visible"
                        or cell.row in hidden_rows
                        or cell.column_letter in hidden_cols,
                        comment=cell.comment.text.strip() if cell.comment else None,
                    )

            # Fill merged ranges from their top-left cell so headers and grouped rows are complete.
            for rng in ws.merged_cells.ranges:
                origin = sheet.get(rng.min_row, rng.min_col)
                if origin is None:
                    continue
                for r in range(rng.min_row, rng.max_row + 1):
                    for c in range(rng.min_col, rng.max_col + 1):
                        if (r, c) == (rng.min_row, rng.min_col):
                            continue
                        sheet.cells[(r, c)] = RawCell(
                            sheet=ws.title,
                            row=r,
                            col=c,
                            value=origin.value,
                            value_type=origin.value_type,
                            number_format=origin.number_format,
                            hidden=origin.hidden,
                            merged_from=origin.coordinate,
                        )
            if formulas_without_cache:
                warnings.append(
                    f"{file_name} › {ws.title}: {formulas_without_cache} formula cell(s) have no "
                    "cached value (file was never recalculated in Excel); shown as empty"
                )
            sheets.append(sheet)
    finally:
        wb_f.close()
        wb_v.close()
    return Workbook(file_name=file_name, sheets=sheets, file_format="xlsx", warnings=warnings)


# ---------------------------------------------------------------------------------------- xls


def _read_xls(data: bytes, file_name: str) -> Workbook:
    import xlrd

    book = xlrd.open_workbook(file_contents=data, formatting_info=True)
    warnings: list[str] = []
    sheets: list[Sheet] = []
    for sh in book.sheets():
        state = {0: "visible", 1: "hidden", 2: "veryHidden"}.get(sh.visibility, "visible")
        sheet = Sheet(name=sh.name, state=state)  # type: ignore[arg-type]
        if state != "visible":
            warnings.append(f"{file_name} › {sh.name}: sheet is {state}; read and tagged")
        for r in range(sh.nrows):
            row_hidden = bool(getattr(sh.rowinfo_map.get(r), "hidden", False))
            for c in range(sh.ncols):
                cell = sh.cell(r, c)
                if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                    continue
                vtype: ValueType
                value: object = cell.value
                if cell.ctype == xlrd.XL_CELL_NUMBER:
                    vtype = "number"
                elif cell.ctype == xlrd.XL_CELL_DATE:
                    vtype = "date"
                    value = xlrd.xldate.xldate_as_datetime(float(cell.value), book.datemode)
                elif cell.ctype == xlrd.XL_CELL_BOOLEAN:
                    vtype, value = "bool", bool(cell.value)
                elif cell.ctype == xlrd.XL_CELL_ERROR:
                    vtype = "error"
                    value = xlrd.error_text_from_code.get(int(cell.value), "#ERR")
                else:
                    vtype = "text"
                col_hidden = bool(getattr(sh.colinfo_map.get(c), "hidden", False))
                sheet.cells[(r + 1, c + 1)] = RawCell(
                    sheet=sh.name,
                    row=r + 1,
                    col=c + 1,
                    value=value,  # type: ignore[arg-type]
                    value_type=vtype,
                    hidden=state != "visible" or row_hidden or col_hidden,
                )
        for rlo, rhi, clo, chi in sh.merged_cells:
            origin = sheet.get(rlo + 1, clo + 1)
            if origin is None:
                continue
            for r in range(rlo, rhi):
                for c in range(clo, chi):
                    if (r, c) != (rlo, clo):
                        sheet.cells[(r + 1, c + 1)] = RawCell(
                            sheet=sh.name,
                            row=r + 1,
                            col=c + 1,
                            value=origin.value,
                            value_type=origin.value_type,
                            hidden=origin.hidden,
                            merged_from=origin.coordinate,
                        )
        sheets.append(sheet)
    return Workbook(file_name=file_name, sheets=sheets, file_format="xls", warnings=warnings)


# ---------------------------------------------------------------------------------------- csv


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _read_csv(data: bytes, file_name: str) -> Workbook:
    text = _decode(data)
    try:
        dialect: type[csv.Dialect] | csv.Dialect = csv.Sniffer().sniff(
            text[:8192], delimiters=",;\t|"
        )
    except csv.Error:
        dialect = csv.excel
    stem = file_name.rsplit(".", 1)[0]
    sheet = Sheet(name=stem)
    for r, row in enumerate(csv.reader(io.StringIO(text), dialect), start=1):
        for c, raw in enumerate(row, start=1):
            if raw.strip() == "":
                continue
            # CSV has no types; numbers that look numeric are typed so part keys normalise.
            value: str | int | float = raw
            vtype: ValueType = "text"
            stripped = raw.strip()
            leading_zero_id = stripped.startswith("0") and len(stripped) > 1 and "." not in stripped
            if _CSV_NUMBER_RE.match(stripped) and not leading_zero_id:
                value = float(stripped) if "." in stripped else int(stripped)
                vtype = "number"
            sheet.cells[(r, c)] = RawCell(sheet=stem, row=r, col=c, value=value, value_type=vtype)
    return Workbook(file_name=file_name, sheets=[sheet], file_format="csv")
