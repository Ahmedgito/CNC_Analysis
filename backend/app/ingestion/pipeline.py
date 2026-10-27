"""Workbook -> per-part record fragments, and fragments -> merged ``PartRecord``.

Pure functions, no I/O beyond reading the file. Persistence lives in the repository layer.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from app.domain.record import (
    CellRef,
    ColumnInfo,
    PartRecord,
    RecordRow,
    SheetSlice,
    SourceStatus,
    make_cell_id,
)
from app.ingestion.canonical import FIELD_LABELS, CanonicalField
from app.ingestion.cells import RawCell, Sheet, Workbook, normalize_for_match
from app.ingestion.headers import TableLayout, detect_layout
from app.ingestion.parts import looks_like_part_id, part_key_from_cell, split_part_key
from app.ingestion.readers import read_workbook_bytes

_ROW_SHEET_FIELDS = {CanonicalField.OPERATION_NUMBER, CanonicalField.OPERATION, CanonicalField.TOOL}
_NULLISH = {"", "none", "n/a", "na", "-", "--", "nil", "null"}


@dataclass(slots=True)
class PartFragment:
    part_key: str
    display_part_number: str
    sheets: list[SheetSlice] = field(default_factory=list)


@dataclass(slots=True)
class SheetSummary:
    sheet: str
    state: str
    header_row: int | None
    kind: str | None
    part_column: str | None
    parts: int
    mapped_columns: dict[str, str | None]


@dataclass(slots=True)
class IngestResult:
    file_name: str
    sha256: str
    file_format: str
    fragments: dict[str, PartFragment]
    cells: list[tuple[CellRef, str | None]]  # every non-empty cell with its part key (or None)
    sheets: list[SheetSummary]
    warnings: list[str]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ingest_path(path: Path | str) -> IngestResult:
    path = Path(path)
    return ingest_bytes(path.read_bytes(), path.name)


def ingest_bytes(data: bytes, file_name: str) -> IngestResult:
    workbook = read_workbook_bytes(data, file_name)
    return extract(workbook, sha256_bytes(data))


def _cell_ref(wb: Workbook, cell: RawCell, layout: TableLayout | None) -> CellRef:
    column = layout.column(cell.col) if layout else None
    if layout and cell.row <= (layout.unit_row or layout.header_row):
        header, canonical, unit = "(header/banner)", None, None
    elif column:
        header = column.header
        canonical = column.match.canonical.value if column.match.canonical else None
        unit = column.match.unit
    else:
        header, canonical, unit = f"Column {cell.col_letter}", None, None
    return CellRef(
        cell_id=make_cell_id(wb.file_stem, cell.sheet, cell.col_letter, cell.row),
        file=wb.file_name,
        sheet=cell.sheet,
        row=cell.row,
        col=cell.col_letter,
        header=header,
        canonical=canonical,
        unit=unit,
        value=cell.display_text,
        value_type=cell.value_type,
        hidden=cell.hidden,
        comment=cell.comment,
        formula=cell.formula,
    )


def _find_part_column(sheet: Sheet, layout: TableLayout, known_keys: set[str]) -> int | None:
    for col in layout.columns:
        if col.match.canonical == CanonicalField.PART_NUMBER:
            return col.col
    # Fallback 1: the column whose values overlap most with part keys seen in other sheets.
    best: tuple[float, int | None] = (0.0, None)
    for col in layout.columns:
        keys = [
            part_key_from_cell(sheet.get(r, col.col))
            for r in range(layout.first_data_row, sheet.max_row + 1)
        ]
        keys = [k for k in keys if k]
        if not keys:
            continue
        overlap = sum(k in known_keys for k in keys) / len(keys)
        if overlap > best[0]:
            best = (overlap, col.col)
    if best[1] is not None and best[0] >= 0.5:
        return best[1]
    # Fallback 2: the first column whose values mostly look like part identifiers.
    for col in layout.columns:
        keys = [
            part_key_from_cell(sheet.get(r, col.col))
            for r in range(layout.first_data_row, sheet.max_row + 1)
        ]
        keys = [k for k in keys if k]
        if keys and sum(looks_like_part_id(k) for k in keys) / len(keys) >= 0.8:
            return col.col
    return None


def _op_sort_key(row: RecordRow) -> tuple[float, int]:
    for c in row.cells:
        if c.canonical == CanonicalField.OPERATION_NUMBER.value:
            try:
                return (float(c.value), row.row)
            except ValueError:
                break
    return (float("inf"), row.row)


def extract(wb: Workbook, sha256: str) -> IngestResult:
    warnings = list(wb.warnings)
    fragments: dict[str, PartFragment] = {}
    all_cells: list[tuple[CellRef, str | None]] = []
    summaries: list[SheetSummary] = []
    layouts: dict[str, TableLayout | None] = {s.name: detect_layout(s) for s in wb.sheets}

    # Sheets with a recognised part column go first so fallbacks can use their keys.
    known_keys: set[str] = set()
    ordered = sorted(
        wb.sheets,
        key=lambda s: (
            not any(
                c.match.canonical == CanonicalField.PART_NUMBER
                for c in (layouts[s.name].columns if layouts[s.name] else [])  # type: ignore[union-attr]
            )
        ),
    )
    for sheet in ordered:
        layout = layouts[sheet.name]
        if layout is None:
            for cell in sheet.cells.values():
                if not cell.is_empty and cell.merged_from is None:
                    all_cells.append((_cell_ref(wb, cell, None), None))
            warnings.append(
                f"{wb.file_name} › {sheet.name}: no table header found; not linked to parts"
            )
            summaries.append(SheetSummary(sheet.name, sheet.state, None, None, None, 0, {}))
            continue

        part_col = _find_part_column(sheet, layout, known_keys)
        banner_refs = [_cell_ref(wb, c, layout) for c in layout.banner if c.merged_from is None]
        columns = [
            ColumnInfo(
                col=c.letter,
                header=c.header,
                canonical=c.match.canonical.value if c.match.canonical else None,
                unit=c.match.unit,
            )
            for c in layout.columns
        ]
        rows_by_key: dict[str, list[RecordRow]] = defaultdict(list)
        display_by_key: dict[str, str] = {}
        forward_filled = 0
        last_key: str | None = None

        for r in range(layout.first_data_row, sheet.max_row + 1):
            row_cells = [
                sheet.get(r, col.col) for col in layout.columns if sheet.get(r, col.col) is not None
            ]
            row_cells = [c for c in row_cells if c is not None and not c.is_empty]
            if not row_cells:
                last_key = None if part_col is None else last_key
                continue
            key = part_key_from_cell(sheet.get(r, part_col)) if part_col else None
            if key is None and part_col is not None and last_key is not None:
                key, forward_filled = last_key, forward_filled + 1
            refs = [_cell_ref(wb, c, layout) for c in row_cells]
            for ref in refs:
                all_cells.append((ref, key))
            if key is None:
                continue
            last_key = key
            pk_cell = sheet.get(r, part_col) if part_col else None
            display_by_key.setdefault(key, pk_cell.display_text if pk_cell else key)
            rows_by_key[key].append(RecordRow(row=r, cells=refs))

        for cell in layout.banner:
            if cell.merged_from is None:
                all_cells.append((_cell_ref(wb, cell, layout), None))
        for cell in sheet.row_cells(layout.header_row):
            all_cells.append((_cell_ref(wb, cell, layout), None))

        if part_col is None:
            warnings.append(
                f"{wb.file_name} › {sheet.name}: no part-number column found; not linked to parts"
            )
        if forward_filled:
            warnings.append(
                f"{wb.file_name} › {sheet.name}: {forward_filled} row(s) had a blank part number "
                "and were attached to the part above"
            )

        has_row_fields = any(c.match.canonical in _ROW_SHEET_FIELDS for c in layout.columns)
        multi = any(len(v) > 1 for v in rows_by_key.values())
        kind = "rows" if (multi or has_row_fields) else "attributes"
        for key, rows in rows_by_key.items():
            if kind == "rows":
                rows = sorted(rows, key=_op_sort_key)
            frag = fragments.setdefault(key, PartFragment(key, display_by_key[key]))
            frag.sheets.append(
                SheetSlice(
                    file=wb.file_name,
                    sheet=sheet.name,
                    kind=kind,  # type: ignore[arg-type]
                    header_row=layout.header_row,
                    hidden=sheet.state != "visible",
                    columns=columns,
                    rows=rows,
                    banner=banner_refs,
                )
            )
        known_keys |= set(rows_by_key)
        part_column = layout.column(part_col) if part_col else None
        summaries.append(
            SheetSummary(
                sheet=sheet.name,
                state=sheet.state,
                header_row=layout.header_row,
                kind=kind if part_col else None,
                part_column=part_column.header if part_column else None,
                parts=len(rows_by_key),
                mapped_columns={
                    c.header: c.match.canonical.value if c.match.canonical else None
                    for c in layout.columns
                },
            )
        )
    return IngestResult(
        file_name=wb.file_name,
        sha256=sha256,
        file_format=wb.file_format,
        fragments=fragments,
        cells=all_cells,
        sheets=summaries,
        warnings=warnings,
    )


# ------------------------------------------------------------------------------------ merging


def _is_nullish(value: str) -> bool:
    return normalize_for_match(value) in _NULLISH


def merge_fragments(
    part_key: str,
    fragments: list[PartFragment],
    other_sources: dict[str, SourceStatus] | None = None,
) -> PartRecord:
    """Combine one part's fragments from several workbooks into a single record."""
    sheets = [s for f in fragments for s in f.sheets]
    sheets.sort(key=lambda s: (s.file, s.kind != "attributes", s.sheet))
    display = fragments[0].display_part_number if fragments else part_key
    base, suffix = split_part_key(part_key)

    present: dict[str, None] = {}
    unmapped: dict[str, None] = {}
    for s in sheets:
        for row in s.rows:
            for c in row.cells:
                # A literal "None" (e.g. Holes: None) is information, so it still counts as present.
                if c.canonical:
                    label = FIELD_LABELS.get(CanonicalField(c.canonical), c.canonical)
                    present.setdefault(label)
                else:
                    unmapped.setdefault(f'"{c.header}" column')

    warnings: list[str] = []
    seen: dict[str, tuple[str, CellRef]] = {}
    for s in sheets:
        if s.kind != "attributes":
            continue
        for row in s.rows:
            for c in row.cells:
                if not c.canonical or c.canonical == CanonicalField.PART_NUMBER.value:
                    continue
                norm = normalize_for_match(c.value)
                prior = seen.get(c.canonical)
                if prior is None:
                    seen[c.canonical] = (norm, c)
                elif prior[0] != norm and not _is_nullish(c.value):
                    warnings.append(
                        f"Conflict in {c.canonical}: '{prior[1].value}' ({prior[1].cell_id}) vs "
                        f"'{c.value}' ({c.cell_id})"
                    )

    files = sorted({s.file for s in sheets})
    sources: dict[str, SourceStatus] = {
        "excel": SourceStatus(available=bool(files), files=files),
        "pdf": SourceStatus(available=False, note="PDF drawings are not ingested yet (Level 2)"),
        "iges": SourceStatus(available=False, note="IGES models are not ingested yet (Level 3)"),
    }
    if other_sources:
        sources.update(other_sources)
    if any(s.hidden for s in sheets):
        warnings.append("Some values come from hidden sheets/rows; treat them with care")

    return PartRecord(
        part_key=part_key,
        display_part_number=display,
        base_key=base,
        suffix=suffix,
        sources=sources,  # type: ignore[arg-type]
        sheets=sheets,
        available_fields=list(present) + list(unmapped),
        warnings=warnings,
    )
