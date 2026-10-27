from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, UploadFile

from app.api.deps import ProblemError, SessionDep, SettingsDep
from app.api.schemas import FileIngestOut, IngestOut, IngestRunOut, SheetIngestOut
from app.ingestion.readers import SUPPORTED_SUFFIXES, UnsupportedFileError
from app.repositories.parts import list_runs
from app.services.ingest_service import ingest_file_bytes

router = APIRouter(tags=["ingest"])


@router.post("/ingest", response_model=IngestOut, summary="Upload and ingest spreadsheets")
def ingest(
    session: SessionDep,
    settings: SettingsDep,
    files: Annotated[list[UploadFile], File(description=".xlsx, .xls or .csv files")],
) -> IngestOut:
    out: list[FileIngestOut] = []
    limit = settings.max_upload_mb * 1024 * 1024
    for upload in files:
        name = (upload.filename or "upload").replace("\\", "/").rsplit("/", 1)[-1]
        if not any(name.lower().endswith(s) for s in SUPPORTED_SUFFIXES):
            raise ProblemError(
                415, "Unsupported file", f"{name}: expected one of {sorted(SUPPORTED_SUFFIXES)}"
            )
        data = upload.file.read(limit + 1)
        if len(data) > limit:
            raise ProblemError(413, "File too large", f"{name} exceeds {settings.max_upload_mb} MB")
        try:
            outcome = ingest_file_bytes(session, data, name)
        except UnsupportedFileError as exc:
            raise ProblemError(415, "Unsupported file", str(exc)) from exc
        out.append(
            FileIngestOut(
                file_name=outcome.file_name,
                run_id=outcome.run_id,
                status=outcome.status,
                parts=outcome.parts,
                superseded_runs=outcome.superseded_runs,
                warnings=outcome.warnings,
                sheets=[SheetIngestOut(**s) for s in outcome.sheets],
            )
        )
    return IngestOut(files=out)


@router.get("/ingest/runs", response_model=list[IngestRunOut], summary="Ingest history")
def runs(session: SessionDep) -> list[IngestRunOut]:
    return [IngestRunOut.model_validate(r, from_attributes=True) for r in list_runs(session)]
