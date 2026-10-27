"""Persistence for ingest runs, cells, drawing and model facts, part fragments and part records.

Records are rebuilt per *base number* group: every active fragment whose part number has the same
base (``P-3001``, ``3001``, ``003003`` -> ``3003``, ``3004-A`` -> ``3004``) is loaded, grouped by
identity key, and merged. A drawing- or model-only identity (``3004`` from a title block or a
file name) joins the one spreadsheet record with that base number (``3004-A``) when exactly one
exists; otherwise it stays a record of its own, so a file is never attached to a guessed part.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process
from sqlalchemy import delete, insert, or_, select, update
from sqlalchemy.orm import Session

from app.db.models import (
    CellRow,
    DrawingFactRow,
    IngestRun,
    ModelFactRow,
    PartFragmentRow,
    PartRow,
)
from app.domain.drawing import DrawingSlice
from app.domain.model import ModelSlice, make_model_fact_id
from app.domain.record import PartRecord, PartSummary, SheetSlice
from app.ingestion.model import ModelIngestResult
from app.ingestion.parts import base_of, identity_key, split_part_key
from app.ingestion.pdf import DrawingIngestResult
from app.ingestion.pipeline import IngestResult, PartFragment, merge_fragments

_CELL_BATCH = 1000


@dataclass(slots=True)
class IngestOutcome:
    file_name: str
    run_id: uuid.UUID | None
    status: str  # created | duplicate | failed
    parts: list[str] = field(default_factory=list)
    superseded_runs: int = 0
    warnings: list[str] = field(default_factory=list)
    sheets: list[dict] = field(default_factory=list)
    kind: str = "workbook"  # workbook | drawing | model
    drawing: dict | None = None  # summary for drawings: pages, scanned, linked part, ...
    model: dict | None = None  # summary for models: topology, units, features, linked part


def _duplicate(
    session: Session, sha256: str, file_name: str, parts: list[str]
) -> IngestOutcome | None:
    existing = session.scalar(select(IngestRun).where(IngestRun.file_sha256 == sha256))
    if existing is None:
        return None
    return IngestOutcome(
        file_name=file_name,
        run_id=existing.id,
        status="duplicate",
        parts=parts,
        warnings=[f"{file_name}: identical file already ingested; nothing changed"],
    )


def _supersede(session: Session, file_name: str) -> tuple[int, set[str], set[str]]:
    """Retire active runs of the same file name. Returns (count, affected bases, raw keys)."""
    previous = session.scalars(
        select(IngestRun).where(IngestRun.file_name == file_name, IngestRun.status == "active")
    ).all()
    bases: set[str] = set()
    keys: set[str] = set()
    for run in previous:
        for key, base in session.execute(
            select(PartFragmentRow.part_key, PartFragmentRow.base_key).where(
                PartFragmentRow.run_id == run.id
            )
        ):
            keys.add(key)
            bases.add(base or base_of(key))
        session.execute(delete(PartFragmentRow).where(PartFragmentRow.run_id == run.id))
    if previous:
        session.execute(
            update(IngestRun)
            .where(IngestRun.id.in_([r.id for r in previous]))
            .values(status="superseded")
        )
    return len(previous), bases, keys


def save_ingest(session: Session, result: IngestResult) -> IngestOutcome:
    """Persist one ingested workbook.

    Identical bytes are a no-op; a changed file with the same name supersedes the old version.
    """
    dup = _duplicate(session, result.sha256, result.file_name, sorted(result.fragments))
    if dup is not None:
        return dup

    superseded, bases, old_keys = _supersede(session, result.file_name)
    bases |= {base_of(k) for k in result.fragments}

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
            "part_key": identity_key(key) if key else None,
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
                base_key=base_of(key),
                kind="sheet",
                display_part_number=frag.display_part_number,
                sheets=[s.model_dump(mode="json") for s in frag.sheets],
            )
        )
    session.flush()
    rebuild_bases(session, bases, stale_keys=old_keys)
    return IngestOutcome(
        file_name=result.file_name,
        run_id=run.id,
        status="created",
        parts=sorted(result.fragments),
        superseded_runs=superseded,
        warnings=result.warnings,
        sheets=sheets_meta,
    )


def save_drawing(session: Session, result: DrawingIngestResult) -> IngestOutcome:
    """Persist one ingested PDF drawing and attach it to its part."""
    d = result.slice
    parts = [result.part_key] if result.part_key else []
    dup = _duplicate(session, result.sha256, result.file_name, parts)
    if dup is not None:
        dup.kind, dup.drawing = "drawing", drawing_summary(d, result.part_key)
        return dup

    superseded, bases, old_keys = _supersede(session, result.file_name)
    run = IngestRun(
        file_name=result.file_name,
        file_sha256=result.sha256,
        file_format="pdf",
        status="active",
        part_count=len(parts),
        cell_count=len(d.facts),
        page_count=d.page_count,
        extraction=d.extraction,
        sheets=[p.model_dump(mode="json") for p in d.pages],
        warnings=result.warnings,
    )
    session.add(run)
    session.flush()
    _insert_drawing_facts(session, run.id, d, result.part_key)

    key = result.part_key or ""
    session.add(
        PartFragmentRow(
            run_id=run.id,
            part_key=key,
            base_key=base_of(key) if key else "",
            kind="drawing",
            display_part_number=d.part_number or key,
            sheets=[],
            drawing=d.model_dump(mode="json"),
        )
    )
    session.flush()
    if key:
        bases.add(base_of(key))
    rebuild_bases(session, bases, stale_keys=old_keys)
    return IngestOutcome(
        file_name=result.file_name,
        run_id=run.id,
        status="created",
        parts=parts,
        superseded_runs=superseded,
        warnings=result.warnings,
        kind="drawing",
        drawing=drawing_summary(d, result.part_key),
    )


def _insert_drawing_facts(
    session: Session, run_id: uuid.UUID, d: DrawingSlice, part_key: str | None
) -> None:
    rows = [
        {
            "run_id": run_id,
            "fact_id": f.fact_id,
            "part_key": identity_key(part_key) if part_key else None,
            "file_name": d.file,
            "page": f.page,
            "region": f.region,
            "key": f.key[:64],
            "kind": f.kind,
            "label": f.label,
            "canonical": f.canonical,
            "value": f.value,
            "unit": f.unit,
            "confidence": f.confidence,
            "stale": f.stale,
            "bboxes": f.bboxes,
            "points_to": f.points_to,
        }
        for f in d.facts
    ]
    if rows:
        session.execute(insert(DrawingFactRow), rows)


def drawing_summary(d: DrawingSlice, part_key: str | None) -> dict:
    return {
        "pages": d.page_count,
        "readable": d.readable,
        "scanned": d.scanned,
        "extraction": d.extraction,
        "linked_part": part_key,
        "part_number_source": d.part_number_source,
        "current_revision": d.current_revision,
        "units": d.units,
        "facts": len(d.facts),
        "title_block_fields": sorted({f.key for f in d.facts if f.region == "title_block"}),
    }


def save_model(session: Session, result: ModelIngestResult) -> IngestOutcome:
    """Persist one measured IGES model and attach it to its part."""
    m = result.slice
    parts = [result.part_key] if result.part_key else []
    dup = _duplicate(session, result.sha256, result.file_name, parts)
    if dup is not None:
        dup.kind, dup.model = "model", model_summary(m, result.part_key)
        return dup

    superseded, bases, old_keys = _supersede(session, result.file_name)
    run = IngestRun(
        file_name=result.file_name,
        file_sha256=result.sha256,
        file_format="iges",
        status="active",
        part_count=len(parts),
        cell_count=len(m.features),
        extraction="geometry",
        sheets=[],
        warnings=result.warnings,
    )
    session.add(run)
    session.flush()
    _insert_model_facts(session, run.id, m, result.part_key)
    key = result.part_key or ""
    session.add(
        PartFragmentRow(
            run_id=run.id,
            part_key=key,
            base_key=base_of(key) if key else "",
            kind="model",
            display_part_number=m.part_number or key,
            sheets=[],
            model=m.model_dump(mode="json"),
        )
    )
    session.flush()
    if key:
        bases.add(base_of(key))
    rebuild_bases(session, bases, stale_keys=old_keys)
    return IngestOutcome(
        file_name=result.file_name,
        run_id=run.id,
        status="created",
        parts=parts,
        superseded_runs=superseded,
        warnings=result.warnings,
        kind="model",
        model=model_summary(m, result.part_key),
    )


def _insert_model_facts(
    session: Session, run_id: uuid.UUID, m: ModelSlice, part_key: str | None
) -> None:
    rows = [
        {
            "run_id": run_id,
            "fact_id": make_model_fact_id(m.file_stem, f.feature_id),
            "part_key": identity_key(part_key) if part_key else None,
            "file_name": m.file,
            "feature": f.feature_id[:64],
            "kind": f.kind,
            "label": f.label,
            "canonical": f.canonical,
            "value": f.value,
            "unit": f.unit,
            "numbers": f.numbers,
            "confidence": f.confidence,
            "method": f.method,
            "stale": f.stale,
        }
        for f in m.features
    ]
    if rows:
        session.execute(insert(ModelFactRow), rows)


def model_summary(m: ModelSlice, part_key: str | None) -> dict:
    return {
        "linked_part": part_key,
        "part_number_source": m.part_number_source,
        "topology": m.topology,
        "valid": m.valid,
        "bodies": m.bodies,
        "faces": m.faces,
        "form": m.form,
        "units": m.header.units,
        "units_declared": m.header.units_declared,
        "revision": m.revision,
        "features": len([f for f in m.features if f.kind != "header"]),
        "views": m.views,
    }


def replace_model(session: Session, file_name: str, m: ModelSlice) -> str | None:
    """Swap the stored slice of an active model (after re-extracting with a newer extractor)."""
    frag = session.scalar(
        select(PartFragmentRow)
        .join(IngestRun)
        .where(
            IngestRun.file_name == file_name,
            IngestRun.status == "active",
            PartFragmentRow.kind == "model",
        )
    )
    if frag is None:
        return None
    frag.model = m.model_dump(mode="json")
    session.execute(delete(ModelFactRow).where(ModelFactRow.run_id == frag.run_id))
    _insert_model_facts(session, frag.run_id, m, frag.part_key or None)
    session.flush()
    if frag.part_key:
        rebuild_bases(session, {frag.base_key or base_of(frag.part_key)})
    return frag.part_key or None


def replace_drawing(session: Session, file_name: str, d: DrawingSlice) -> str | None:
    """Swap the stored slice of an active drawing (after a consented vision read)."""
    frag = session.scalar(
        select(PartFragmentRow)
        .join(IngestRun)
        .where(
            IngestRun.file_name == file_name,
            IngestRun.status == "active",
            PartFragmentRow.kind == "drawing",
        )
    )
    if frag is None:
        return None
    frag.drawing = d.model_dump(mode="json")
    run = session.get(IngestRun, frag.run_id)
    if run is not None:
        run.extraction = d.extraction
        run.cell_count = len(d.facts)
    session.execute(delete(DrawingFactRow).where(DrawingFactRow.run_id == frag.run_id))
    _insert_drawing_facts(session, frag.run_id, d, frag.part_key or None)
    session.flush()
    if frag.part_key:
        rebuild_bases(session, {frag.base_key or base_of(frag.part_key)})
    return frag.part_key or None


def _dedupe_cells(result: IngestResult) -> list[tuple]:
    seen: dict[str, tuple] = {}
    for ref, key in result.cells:
        prior = seen.get(ref.cell_id)
        if prior is None or (prior[1] is None and key is not None):
            seen[ref.cell_id] = (ref, key)
    return list(seen.values())


@dataclass(slots=True)
class _Group:
    sheets: list[PartFragment] = field(default_factory=list)
    drawings: list[DrawingSlice] = field(default_factory=list)
    models: list[ModelSlice] = field(default_factory=list)
    raw_keys: set[str] = field(default_factory=set)


def rebuild_bases(session: Session, bases: set[str], stale_keys: set[str] | None = None) -> None:
    """Rebuild every part record whose base number is in ``bases``."""
    for base in sorted(b for b in bases if b):
        frags = session.scalars(
            select(PartFragmentRow)
            .join(IngestRun)
            .where(PartFragmentRow.base_key == base, IngestRun.status == "active")
            .order_by(IngestRun.file_name, PartFragmentRow.id)
        ).all()
        groups: dict[str, _Group] = defaultdict(_Group)
        for f in frags:
            g = groups[identity_key(f.part_key)]
            g.raw_keys.add(f.part_key)
            if f.kind == "drawing" and f.drawing:
                g.drawings.append(DrawingSlice.model_validate(f.drawing))
            elif f.kind == "model" and f.model:
                g.models.append(ModelSlice.model_validate(f.model))
            else:
                g.sheets.append(
                    PartFragment(
                        part_key=f.part_key,
                        display_part_number=f.display_part_number,
                        sheets=[SheetSlice.model_validate(s) for s in f.sheets],
                    )
                )
        anchors = [ident for ident, g in groups.items() if g.sheets]
        final: dict[str, _Group] = defaultdict(_Group)
        for ident, g in groups.items():
            target = ident
            if not g.sheets and len(anchors) == 1:
                target = anchors[0]  # 3004 (title block) joins 3004-A (the only register row)
            final[target].sheets.extend(g.sheets)
            final[target].drawings.extend(g.drawings)
            final[target].models.extend(g.models)
            final[target].raw_keys |= g.raw_keys

        for key, g in final.items():
            record = merge_fragments(key, g.sheets, drawings=g.drawings, models=g.models)
            _upsert_part(session, key, base, record)
        obsolete = select(PartRow.part_key).where(
            PartRow.base_key == base, PartRow.part_key.not_in(list(final) or [""])
        )
        session.execute(delete(PartRow).where(PartRow.part_key.in_(obsolete)))
        # Keys written before identity grouping (e.g. "P-3001", "003003") are retired too, but
        # only within this base group: other groups' records are not this group's to delete.
        candidates = {k for g in final.values() for k in g.raw_keys} | (stale_keys or set())
        retired = {k for k in candidates if base_of(k) == base} - set(final)
        if retired:
            session.execute(delete(PartRow).where(PartRow.part_key.in_(retired)))
    session.flush()


def rebuild_all(session: Session) -> int:
    """Regroup every stored fragment into records (used after upgrading to identity keys)."""
    bases = set(
        session.scalars(
            select(PartFragmentRow.base_key).join(IngestRun).where(IngestRun.status == "active")
        )
    )
    keys = set(
        session.scalars(
            select(PartFragmentRow.part_key).join(IngestRun).where(IngestRun.status == "active")
        )
    )
    for f in session.scalars(select(PartFragmentRow).where(PartFragmentRow.base_key == "")):
        if f.part_key:
            f.base_key = base_of(f.part_key)
            bases.add(f.base_key)
    session.flush()
    session.execute(delete(PartRow))
    rebuild_bases(session, bases, stale_keys=keys)
    return session.query(PartRow).count()


def _upsert_part(session: Session, key: str, base: str, record: PartRecord) -> None:
    _, suffix = split_part_key(key)
    payload = record.model_dump(mode="json")
    row = session.get(PartRow, key)
    if row is None:
        session.add(
            PartRow(
                part_key=key,
                display_part_number=record.display_part_number[:64],
                base_key=base,
                suffix=suffix,
                description=record.description(),
                record=payload,
            )
        )
    else:
        row.display_part_number = record.display_part_number[:64]
        row.base_key, row.suffix = base, suffix
        row.description = record.description()
        row.record = payload


def get_part(session: Session, key: str) -> PartRecord | None:
    row = session.get(PartRow, key)
    return PartRecord.model_validate(row.record) if row else None


def parts_with_base(session: Session, base: str) -> list[str]:
    return list(session.scalars(select(PartRow.part_key).where(PartRow.base_key == base)))


def list_parts(session: Session, query: str | None = None, limit: int = 200) -> list[PartSummary]:
    stmt = select(PartRow).order_by(PartRow.base_key, PartRow.part_key).limit(limit)
    if query:
        like = f"%{query.strip()}%"
        stmt = stmt.where(
            or_(
                PartRow.part_key.ilike(like),
                PartRow.display_part_number.ilike(like),
                PartRow.description.ilike(like),
            )
        )
    out: list[PartSummary] = []
    for row in session.scalars(stmt):
        rec = PartRecord.model_validate(row.record)
        out.append(
            PartSummary(
                part_key=row.part_key,
                display_part_number=row.display_part_number,
                description=row.description,
                sources=rec.sources,
                files=[s for kind in ("excel", "pdf", "iges") for s in rec.sources[kind].files],
            )
        )
    return out


def suggest_parts(session: Session, key: str, limit: int = 5) -> list[str]:
    """Parts that share the base number, then the closest keys by edit similarity."""
    base = base_of(key)
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


def unlinked_drawings(session: Session) -> list[DrawingSlice]:
    rows = session.scalars(
        select(PartFragmentRow)
        .join(IngestRun)
        .where(
            PartFragmentRow.kind == "drawing",
            PartFragmentRow.part_key == "",
            IngestRun.status == "active",
        )
    )
    return [DrawingSlice.model_validate(r.drawing) for r in rows if r.drawing]


def unlinked_models(session: Session) -> list[ModelSlice]:
    rows = session.scalars(
        select(PartFragmentRow)
        .join(IngestRun)
        .where(
            PartFragmentRow.kind == "model",
            PartFragmentRow.part_key == "",
            IngestRun.status == "active",
        )
    )
    return [ModelSlice.model_validate(r.model) for r in rows if r.model]


def drawing_bytes_source(session: Session, file_name: str) -> IngestRun | None:
    """The active ingest run for a drawing file (used to find its bytes in the store)."""
    return session.scalar(
        select(IngestRun).where(
            IngestRun.file_name == file_name,
            IngestRun.status == "active",
            IngestRun.file_format == "pdf",
        )
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
