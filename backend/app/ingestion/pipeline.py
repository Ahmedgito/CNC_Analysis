"""Workbook -> per-part record fragments, and fragments -> merged ``PartRecord``.

Pure functions, no I/O beyond reading the file. Persistence lives in the repository layer.

Real workshop exports are messier than a clean register. Beyond header detection this module
handles:

- separator rows (``-- PLATES --``) in the part-number column, which group parts and are not parts;
- vertical "part card" sheets (labels down column A, one part's values down column B);
- archive / obsolete / history sheets, whose rows are kept as history and marked stale;
- superseded rows (a status such as SUPERSEDED, a remark such as "Replaced by Rev B", or an
  older revision of a part that also has a newer one), also kept and marked stale;
- a sheet-level unit statement in the banner ("Units: mm unless stated").
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from app.domain.drawing import DrawingSlice
from app.domain.record import (
    CellRef,
    ColumnInfo,
    PartRecord,
    RecordRow,
    SheetSlice,
    SourceStatus,
    make_cell_id,
)
from app.ingestion.canonical import FIELD_LABELS, CanonicalField, match_header
from app.ingestion.cells import RawCell, Sheet, Workbook, column_letter, normalize_for_match
from app.ingestion.headers import TableLayout, detect_layout
from app.ingestion.parts import (
    looks_like_part_id,
    normalize_part_key,
    part_key_from_cell,
    split_part_key,
)
from app.ingestion.readers import read_workbook_bytes

_ROW_SHEET_FIELDS = {CanonicalField.OPERATION_NUMBER, CanonicalField.OPERATION, CanonicalField.TOOL}
_NULLISH = {"", "none", "n/a", "na", "-", "--", "nil", "null"}
_STALE_SHEET_RE = re.compile(
    r"\b(archive[ds]?|obsolete|old|superseded|history|historic(?:al)?|deprecated|retired|"
    r"backup|previous)\b"
)
_STALE_VALUE_RE = re.compile(
    r"\b(superseded|obsolete|inactive|retired|cancell?ed|void|withdrawn|replaced by|"
    r"do not use|deprecated)\b",
    re.IGNORECASE,
)
_UNIT_STATEMENT_RE = re.compile(
    r"\b(?:units?|dims?|dimensions?)\b\s*(?:[:=]|are|in)?\s*"
    r"(mm|millimet(?:er|re)s?|inch(?:es)?|in)\b",
    re.IGNORECASE,
)
_CARD_LABEL_SHARE = 0.6


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


def _labelled_ref(wb: Workbook, cell: RawCell, label: str) -> CellRef:
    """A value cell whose meaning comes from a label next to it (part cards)."""
    match = match_header(label)
    return CellRef(
        cell_id=make_cell_id(wb.file_stem, cell.sheet, cell.col_letter, cell.row),
        file=wb.file_name,
        sheet=cell.sheet,
        row=cell.row,
        col=cell.col_letter,
        header=match.label or label,
        canonical=match.canonical.value if match.canonical else None,
        unit=match.unit,
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


def _sheet_stale_reason(name: str) -> str | None:
    words = re.sub(r"[_\-.]+", " ", name).casefold()
    if _STALE_SHEET_RE.search(words):
        return f"from the '{name}' sheet, which holds archived or obsolete data"
    return None


def _banner_unit(banner: list[RawCell]) -> str | None:
    for cell in banner:
        m = _UNIT_STATEMENT_RE.search(cell.display_text)
        if m:
            return "mm" if m.group(1).casefold().startswith("m") else "in"
    return None


def _row_stale_reason(refs: list[CellRef]) -> str | None:
    for c in refs:
        if c.canonical in (CanonicalField.STATUS.value, CanonicalField.REMARKS.value) and (
            _STALE_VALUE_RE.search(c.value)
        ):
            return f"{c.header}: {c.value}"
    return None


def _revision_rank(value: str) -> tuple[int, float, str]:
    v = value.strip().upper()
    try:
        return (1, float(v), v)
    except ValueError:
        return (0, 0.0, v)


def _mark_older_revisions(rows: list[RecordRow]) -> None:
    """When one part has several current rows that differ by revision, keep the newest current."""
    live = [r for r in rows if not r.stale]
    revs: dict[int, str] = {}
    for r in live:
        rev = next(
            (c.value for c in r.cells if c.canonical == CanonicalField.REVISION.value and c.value),
            None,
        )
        if rev is not None:
            revs[r.row] = rev
    if len(live) < 2 or len(revs) != len(live) or len(set(revs.values())) < 2:
        return
    newest = max(revs.values(), key=_revision_rank)
    for r in live:
        if revs[r.row] != newest:
            r.stale = True
            r.stale_reason = f"older revision (Rev {revs[r.row]}; Rev {newest} is current)"


def _card_columns(sheet: Sheet, layout: TableLayout) -> tuple[int, int] | None:
    """(label column, value column) when the sheet is a vertical card for one part."""
    pn_cols = [c for c in layout.columns if c.match.canonical == CanonicalField.PART_NUMBER]
    if len(pn_cols) != 1:
        return None
    id_cols = []
    for c in layout.columns:
        if c is pn_cols[0]:
            continue
        key = normalize_part_key(c.header)
        if key and looks_like_part_id(key):
            id_cols.append(c)
    if len(id_cols) != 1:
        return None
    labels = [sheet.get(r, pn_cols[0].col) for r in range(layout.first_data_row, sheet.max_row + 1)]
    labels = [c for c in labels if c is not None and not c.is_empty]
    if len(labels) < 3:
        return None
    known = sum(match_header(c.display_text).canonical is not None for c in labels)
    if known / len(labels) < _CARD_LABEL_SHARE:
        return None
    return pn_cols[0].col, id_cols[0].col


def _extract_card(
    wb: Workbook, sheet: Sheet, layout: TableLayout, label_col: int, value_col: int
) -> tuple[str, str, SheetSlice, list[tuple[CellRef, str | None]]] | None:
    header_cell = sheet.get(layout.header_row, value_col)
    label_cell = sheet.get(layout.header_row, label_col)
    if header_cell is None or label_cell is None:
        return None
    key = part_key_from_cell(header_cell)
    if key is None:
        return None
    cells: list[tuple[CellRef, str | None]] = []
    refs = [_labelled_ref(wb, header_cell, label_cell.display_text)]
    for r in range(layout.first_data_row, sheet.max_row + 1):
        label, value = sheet.get(r, label_col), sheet.get(r, value_col)
        if label is not None and not label.is_empty:
            cells.append((_cell_ref(wb, label, None), None))
        if label is None or label.is_empty or value is None or value.is_empty:
            continue
        refs.append(_labelled_ref(wb, value, label.display_text))
    cells.extend((ref, key) for ref in refs)
    banner_refs = [_cell_ref(wb, c, layout) for c in layout.banner if c.merged_from is None]
    stale_reason = _sheet_stale_reason(sheet.name)
    slice_ = SheetSlice(
        file=wb.file_name,
        sheet=sheet.name,
        kind="attributes",
        header_row=layout.header_row,
        hidden=sheet.state != "visible",
        columns=[
            ColumnInfo(col=column_letter(label_col), header=label_cell.display_text),
            ColumnInfo(col=column_letter(value_col), header=header_cell.display_text),
        ],
        rows=[RecordRow(row=layout.header_row, cells=refs)],
        banner=banner_refs,
        stale=stale_reason is not None,
        stale_reason=stale_reason,
        layout="card",
        default_unit=_banner_unit(layout.banner),
    )
    return key, header_cell.display_text, slice_, cells


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

        card = _card_columns(sheet, layout)
        if card is not None:
            extracted = _extract_card(wb, sheet, layout, *card)
            if extracted is not None:
                key, display, slice_, cells = extracted
                all_cells.extend(cells)
                all_cells.extend(
                    (_cell_ref(wb, c, layout), None) for c in layout.banner if c.merged_from is None
                )
                fragments.setdefault(key, PartFragment(key, display)).sheets.append(slice_)
                known_keys.add(key)
                summaries.append(
                    SheetSummary(
                        sheet=sheet.name,
                        state=sheet.state,
                        header_row=layout.header_row,
                        kind="card",
                        part_column=slice_.columns[1].header,
                        parts=1,
                        mapped_columns={c.header: c.canonical for c in slice_.rows[0].cells},
                    )
                )
                continue

        part_col = _find_part_column(sheet, layout, known_keys)
        sheet_stale = _sheet_stale_reason(sheet.name)
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
        forward_filled = separators = 0
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
            if key is not None and len(row_cells) == 1 and not looks_like_part_id(key):
                # "-- PLATES --": a group label in the part column, not a part.
                separators += 1
                last_key = None
                all_cells.append((_cell_ref(wb, row_cells[0], layout), None))
                continue
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
            reason = _row_stale_reason(refs)
            rows_by_key[key].append(
                RecordRow(row=r, cells=refs, stale=reason is not None, stale_reason=reason)
            )

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
        if separators:
            warnings.append(
                f"{wb.file_name} › {sheet.name}: {separators} separator row(s) in the part-number "
                "column were treated as group labels, not parts"
            )
        if sheet_stale and rows_by_key:
            warnings.append(
                f"{wb.file_name} › {sheet.name}: archive sheet; its rows are kept as history and "
                "never used as current values"
            )

        has_row_fields = any(c.match.canonical in _ROW_SHEET_FIELDS for c in layout.columns)
        default_unit = _banner_unit(layout.banner)
        sheet_kinds: set[str] = set()
        for key, rows in rows_by_key.items():
            _mark_older_revisions(rows)
            live = [r for r in rows if not r.stale]
            kind = "rows" if (has_row_fields or len(live) > 1) else "attributes"
            sheet_kinds.add(kind)
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
                    stale=sheet_stale is not None,
                    stale_reason=sheet_stale,
                    default_unit=default_unit,
                )
            )
        known_keys |= set(rows_by_key)
        part_column = layout.column(part_col) if part_col else None
        summaries.append(
            SheetSummary(
                sheet=sheet.name,
                state=sheet.state,
                header_row=layout.header_row,
                kind=("rows" if "rows" in sheet_kinds else "attributes") if part_col else None,
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


def _field_label(canonical: str) -> str:
    try:
        return FIELD_LABELS[CanonicalField(canonical)]
    except (KeyError, ValueError):
        return canonical.replace("_", " ")


def _pdf_note(
    drawings: list[DrawingSlice], readable: list[DrawingSlice], scanned: list[str]
) -> str | None:
    if not drawings:
        return "No PDF drawing for this part was found in the ingested files"
    if not readable:
        return (
            f"{', '.join(scanned)}: scanned image with no text layer; it has not been read "
            "(the vision model can read it if the user agrees)"
        )
    return None


def _is_nullish(value: str) -> bool:
    return normalize_for_match(value) in _NULLISH


def _current_rows(sheets: list[SheetSlice]):
    for s in sheets:
        if s.stale:
            continue
        for row in s.rows:
            if not row.stale:
                yield s, row


def merge_fragments(
    part_key: str,
    fragments: list[PartFragment],
    other_sources: dict[str, SourceStatus] | None = None,
    drawings: list[DrawingSlice] | None = None,
) -> PartRecord:
    """Combine one part's fragments from several workbooks and drawings into a single record."""
    from app.services.crosscheck import cross_check, values_agree  # domain service, no I/O

    sheets = [s for f in fragments for s in f.sheets]
    sheets.sort(key=lambda s: (s.stale, s.file, s.kind != "attributes", s.sheet))
    drawings = sorted(drawings or [], key=lambda d: d.file)
    live_fragments = [f for f in fragments if any(not s.stale for s in f.sheets)] or fragments
    display = live_fragments[0].display_part_number if live_fragments else part_key
    if not fragments and drawings:
        display = next((d.part_number for d in drawings if d.part_number), part_key)
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
    for d in drawings:
        for f in d.facts:
            if f.canonical and not f.stale:
                present.setdefault(f"{_field_label(f.canonical)} (drawing)")

    warnings: list[str] = []
    seen: dict[str, tuple[str, CellRef]] = {}
    for s, row in _current_rows(sheets):
        if s.kind != "attributes":
            continue
        for c in row.cells:
            if not c.canonical or c.canonical in (
                CanonicalField.PART_NUMBER.value,
                CanonicalField.LAST_UPDATED.value,
                CanonicalField.STATUS.value,
                CanonicalField.REMARKS.value,
            ):
                continue
            prior = seen.get(c.canonical)
            if prior is None:
                seen[c.canonical] = (normalize_for_match(c.value), c)
            elif (
                prior[0] != normalize_for_match(c.value)
                and not _is_nullish(c.value)
                and not values_agree(c.canonical, prior[1].value, c.value, prior[1].unit, c.unit)
            ):
                warnings.append(
                    f"Conflict in {c.canonical}: '{prior[1].value}' ({prior[1].cell_id}) vs "
                    f"'{c.value}' ({c.cell_id})"
                )
    if any(s.stale or any(r.stale for r in s.rows) for s in sheets):
        warnings.append(
            "Some spreadsheet rows are history (archived sheet or superseded revision); "
            "they are shown but never used as current values"
        )

    files = sorted({s.file for s in sheets})
    readable = [d for d in drawings if d.readable]
    scanned = [d.file for d in drawings if d.scanned]
    current_rev = next((d.current_revision for d in readable if d.current_revision), None)
    sources: dict[str, SourceStatus] = {
        "excel": SourceStatus(available=bool(files), files=files),
        "pdf": SourceStatus(
            available=bool(drawings),
            files=[d.file for d in drawings],
            note=_pdf_note(drawings, readable, scanned),
            readable=bool(readable) if drawings else None,
            scanned=scanned,
            current_revision=current_rev,
        ),
        "iges": SourceStatus(available=False, note="IGES models are not ingested yet (Level 3)"),
    }
    if other_sources:
        sources.update(other_sources)
    if any(s.hidden for s in sheets):
        warnings.append("Some values come from hidden sheets/rows; treat them with care")
    for d in drawings:
        warnings.extend(f"{d.file}: {w}" for w in d.warnings)

    spellings = {f.display_part_number for f in fragments}
    spellings |= {d.part_number for d in drawings if d.part_number}
    aliases = sorted(spellings - {display})
    record = PartRecord(
        part_key=part_key,
        display_part_number=display,
        base_key=base,
        suffix=suffix,
        sources=sources,  # type: ignore[arg-type]
        sheets=sheets,
        available_fields=list(present) + list(unmapped),
        warnings=warnings,
        drawings=drawings,
        aliases=aliases,
    )
    record.cross_checks = cross_check(record)
    return record
