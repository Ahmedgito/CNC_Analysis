"""Persistence for ingest runs, cells, part fragments and merged part records."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process
from sqlalchemy import delete, insert, or_, select, update
from sqlalchemy.orm import Session

from app.db.models import CellRow, IngestRun, PartFragmentRow, PartRow
from app.domain.record import PartRecord, PartSummary, SheetSlice
from app.ingestion.parts import split_part_key
from app.ingestion.pipeline import IngestResult, PartFragment, merge_fragments

_CELL_BATCH = 1000


@dataclass(slots=True)
class IngestOutcome:
    file_name: str
    run_id: uuid.UUID | None
    status: str  # created | duplicate
    parts: list[str] = field(default_factory=list)
    superseded_runs: int = 0
    warnings: list[str] = field(default_factory=list)
    sheets: list[dict] = field(default_factory=list)


def save_ingest(session: Session, result: IngestResult) -> IngestOutcome:
    """Persist one ingested file.

    Identical bytes are a no-op; a changed file with the same name supersedes the old version.
    """
    existing = session.scalar(select(IngestRun).where(IngestRun.file_sha256 == result.sha256))
    if existing is not None:
        return IngestOutcome(
            file_name=result.file_name,
            run_id=existing.id,
            status="duplicate",
            parts=sorted(result.fragments),
            warnings=[f"{result.file_name}: identical file already ingested; nothing changed"],
        )

    previous = session.scalars(
        select(IngestRun).where(
            IngestRun.file_name == result.file_name, IngestRun.status == "active"
        )
    ).all()
    affected: set[str] = set(result.fragments)
    for run in previous:
        affected |= set(
            session.scalars(
                select(PartFragmentRow.part_key).where(PartFragmentRow.run_id == run.id)
            )
        )
        session.execute(delete(PartFragmentRow).where(PartFragmentRow.run_id == run.id))
    if previous:
        session.execute(
            update(IngestRun)
            .where(IngestRun.id.in_([r.id for r in previous]))
            .values(status="superseded")
        )

    sheets_meta = [
        {
            "sheet": s.sheet,
            "state": s.state,
            "header_row": s.header_row,
            "kind": s.kind,
            "part_column": s.part_column,
            "parts": s.parts,
            "mapped_columns": s.mapped_columns,
        }
        for s in result.sheets
    ]
    run = IngestRun(
        file_name=result.file_name,
        file_sha256=result.sha256,
        file_format=result.file_format,
        status="active",
        part_count=len(result.fragments),
        cell_count=len(result.cells),
        sheets=sheets_meta,
        warnings=result.warnings,
    )
    session.add(run)
    session.flush()

    rows = [
        {
            "run_id": run.id,
            "cell_id": ref.cell_id,
            "part_key": key,
            "file_name": ref.file,
            "sheet": ref.sheet,
            "row_num": ref.row,
            "col": ref.col,
            "header": ref.header,
            "canonical": ref.canonical,
            "unit": ref.unit,
            "value": ref.value,
            "value_type": ref.value_type,
            "hidden": ref.hidden,
            "comment": ref.comment,
            "formula": ref.formula,
        }
        for ref, key in _dedupe_cells(result)
    ]
    for i in range(0, len(rows), _CELL_BATCH):
        session.execute(insert(CellRow), rows[i : i + _CELL_BATCH])

    for key, frag in result.fragments.items():
        session.add(
            PartFragmentRow(
                run_id=run.id,
                part_key=key,
                display_part_number=frag.display_part_number,
                sheets=[s.model_dump(mode="json") for s in frag.sheets],
            )
        )
    session.flush()
    rebuild_parts(session, affected)
    return IngestOutcome(
        file_name=result.file_name,
        run_id=run.id,
        status="created",
        parts=sorted(result.fragments),
        superseded_runs=len(previous),
        warnings=result.warnings,
        sheets=sheets_meta,
    )


def _dedupe_cells(result: IngestResult) -> list[tuple]:
    seen: dict[str, tuple] = {}
    for ref, key in result.cells:
        prior = seen.get(ref.cell_id)
        if prior is None or (prior[1] is None and key is not None):
            seen[ref.cell_id] = (ref, key)
    return list(seen.values())


def rebuild_parts(session: Session, keys: set[str]) -> None:
    for key in keys:
        frags = session.scalars(
            select(PartFragmentRow)
            .join(IngestRun)
            .where(PartFragmentRow.part_key == key, IngestRun.status == "active")
            .order_by(IngestRun.file_name)
        ).all()
        if not frags:
            session.execute(delete(PartRow).where(PartRow.part_key == key))
            continue
        record = merge_fragments(
            key,
            [
                PartFragment(
                    part_key=key,
                    display_part_number=f.display_part_number,
                    sheets=[SheetSlice.model_validate(s) for s in f.sheets],
                )
                for f in frags
            ],
        )
        base, suffix = split_part_key(key)
        payload = record.model_dump(mode="json")
        row = session.get(PartRow, key)
        if row is None:
            session.add(
                PartRow(
                    part_key=key,
                    display_part_number=record.display_part_number,
                    base_key=base,
                    suffix=suffix,
                    description=record.description(),
                    record=payload,
                )
            )
        else:
            row.display_part_number = record.display_part_number
            row.base_key, row.suffix = base, suffix
            row.description = record.description()
            row.record = payload
    session.flush()


def get_part(session: Session, key: str) -> PartRecord | None:
    row = session.get(PartRow, key)
    return PartRecord.model_validate(row.record) if row else None


def list_parts(session: Session, query: str | None = None, limit: int = 200) -> list[PartSummary]:
    stmt = select(PartRow).order_by(PartRow.base_key, PartRow.part_key).limit(limit)
    if query:
        like = f"%{query.strip()}%"
        stmt = stmt.where(or_(PartRow.part_key.ilike(like), PartRow.description.ilike(like)))
    out: list[PartSummary] = []
    for row in session.scalars(stmt):
        rec = PartRecord.model_validate(row.record)
        out.append(
            PartSummary(
                part_key=row.part_key,
                display_part_number=row.display_part_number,
                description=row.description,
                sources=rec.sources,
                files=rec.sources["excel"].files,
            )
        )
    return out


def suggest_parts(session: Session, key: str, limit: int = 5) -> list[str]:
    """Parts that share the base number, then the closest keys by edit similarity."""
    base, _ = split_part_key(key)
    same_base = list(
        session.scalars(
            select(PartRow.part_key)
            .where(PartRow.base_key == base, PartRow.part_key != key)
            .limit(limit)
        )
    )
    if len(same_base) >= limit:
        return same_base
    all_keys = list(session.scalars(select(PartRow.part_key)))
    close = [
        k
        for k, score, _ in process.extract(key, all_keys, scorer=fuzz.ratio, limit=limit)
        if score >= 60 and k not in same_base and k != key
    ]
    return (same_base + close)[:limit]


def list_runs(session: Session, limit: int = 50) -> list[IngestRun]:
    return list(
        session.scalars(select(IngestRun).order_by(IngestRun.created_at.desc()).limit(limit))
    )


def cells_for_part(session: Session, key: str) -> list[CellRow]:
    return list(
        session.scalars(
            select(CellRow)
            .join(IngestRun)
            .where(CellRow.part_key == key, IngestRun.status == "active")
            .order_by(CellRow.file_name, CellRow.sheet, CellRow.row_num, CellRow.col)
        )
    )
