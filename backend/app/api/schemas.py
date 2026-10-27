"""HTTP request/response models (domain models are reused where they fit)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.record import PartRecord, PartSummary


class HealthOut(BaseModel):
    status: str


class ReadyOut(BaseModel):
    status: str
    database: bool
    parts: int
    providers: dict[str, bool]


class PartListOut(BaseModel):
    parts: list[PartSummary]
    total: int


class PartOut(BaseModel):
    record: PartRecord
    related: list[str] = Field(
        default_factory=list, description="Other parts sharing the base number"
    )


class SheetIngestOut(BaseModel):
    sheet: str
    state: str
    header_row: int | None
    kind: str | None
    part_column: str | None
    parts: int
    mapped_columns: dict[str, str | None]


class FileIngestOut(BaseModel):
    file_name: str
    run_id: uuid.UUID | None
    status: str
    parts: list[str]
    superseded_runs: int
    warnings: list[str]
    sheets: list[SheetIngestOut]


class IngestOut(BaseModel):
    files: list[FileIngestOut]


class IngestRunOut(BaseModel):
    id: uuid.UUID
    file_name: str
    file_sha256: str
    file_format: str
    status: str
    part_count: int
    cell_count: int
    warnings: list[str]
    created_at: datetime
