"""PDF engineering drawings: extraction of title block, notes, dimensions and revisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.domain.drawing import DrawingSlice
from app.ingestion.pdf.document import MAX_CHARS, MAX_PAGES, UnreadableDocumentError, read_drawing

__all__ = ["DrawingIngestResult", "UnreadableDocumentError", "ingest_drawing_bytes"]


@dataclass(slots=True)
class DrawingIngestResult:
    file_name: str
    sha256: str
    slice: DrawingSlice
    part_key: str | None  # normalised part number the drawing belongs to, None if unidentifiable
    warnings: list[str] = field(default_factory=list)


def ingest_drawing_bytes(
    data: bytes, file_name: str, max_pages: int = MAX_PAGES, max_chars: int = MAX_CHARS
) -> DrawingIngestResult:
    from app.ingestion.pipeline import sha256_bytes

    sha = sha256_bytes(data)
    drawing, key = read_drawing(data, file_name, sha, max_pages, max_chars)
    return DrawingIngestResult(file_name, sha, drawing, key, list(drawing.warnings))


def ingest_drawing_path(path: Path | str, max_pages: int = MAX_PAGES) -> DrawingIngestResult:
    path = Path(path)
    return ingest_drawing_bytes(path.read_bytes(), path.name, max_pages)
