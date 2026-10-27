"""Ingest files or directories into the database: workbooks and PDF drawings."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.db.session import session_scope
from app.ingestion.pdf import UnreadableDocumentError, ingest_drawing_bytes
from app.ingestion.pipeline import ingest_bytes
from app.ingestion.readers import SUPPORTED_SUFFIXES, UnsupportedFileError, sniff_format
from app.logging_setup import log
from app.repositories.parts import IngestOutcome, save_drawing, save_ingest
from app.services.file_store import FileStore


def ingest_file_bytes(
    session: Session,
    data: bytes,
    file_name: str,
    store: FileStore | None = None,
    pdf_max_pages: int = 20,
) -> IngestOutcome:
    if sniff_format(data, file_name) == "pdf":
        drawing = ingest_drawing_bytes(data, file_name, max_pages=pdf_max_pages)
        if store is not None:
            store.put(drawing.sha256, data)
        outcome = save_drawing(session, drawing)
    else:
        outcome = save_ingest(session, ingest_bytes(data, file_name))
    log.info(
        "ingest.file",
        file=file_name,
        kind=outcome.kind,
        status=outcome.status,
        parts=len(outcome.parts),
        warnings=len(outcome.warnings),
    )
    return outcome


def discover_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(
        p
        for p in path.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES and not p.name.startswith("~$")
    )


def ingest_paths(
    factory: sessionmaker[Session],
    path: Path,
    store: FileStore | None = None,
    pdf_max_pages: int = 20,
) -> list[IngestOutcome]:
    """Ingest every supported file under ``path``. Each file commits independently."""
    outcomes: list[IngestOutcome] = []
    for file in discover_files(path):
        try:
            with session_scope(factory) as session:
                outcomes.append(
                    ingest_file_bytes(session, file.read_bytes(), file.name, store, pdf_max_pages)
                )
        except (UnsupportedFileError, UnreadableDocumentError, ValueError, OSError) as exc:
            log.warning("ingest.failed", file=file.name, error=str(exc))
            outcomes.append(
                IngestOutcome(
                    file_name=file.name, run_id=None, status="failed", warnings=[str(exc)]
                )
            )
    return outcomes
