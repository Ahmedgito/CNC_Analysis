"""Ingest files or directories into the database."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.db.session import session_scope
from app.ingestion.pipeline import ingest_bytes
from app.ingestion.readers import SUPPORTED_SUFFIXES, UnsupportedFileError
from app.logging_setup import log
from app.repositories.parts import IngestOutcome, save_ingest


def ingest_file_bytes(session: Session, data: bytes, file_name: str) -> IngestOutcome:
    result = ingest_bytes(data, file_name)
    outcome = save_ingest(session, result)
    log.info(
        "ingest.file",
        file=file_name,
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


def ingest_paths(factory: sessionmaker[Session], path: Path) -> list[IngestOutcome]:
    """Ingest every supported file under ``path``. Each file commits independently."""
    outcomes: list[IngestOutcome] = []
    for file in discover_files(path):
        try:
            with session_scope(factory) as session:
                outcomes.append(ingest_file_bytes(session, file.read_bytes(), file.name))
        except (UnsupportedFileError, ValueError, OSError) as exc:
            log.warning("ingest.failed", file=file.name, error=str(exc))
            outcomes.append(
                IngestOutcome(
                    file_name=file.name, run_id=None, status="failed", warnings=[str(exc)]
                )
            )
    return outcomes
