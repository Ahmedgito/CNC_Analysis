from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Request, UploadFile

from app.api.deps import ProblemError, SessionDep, SettingsDep, StoreDep
from app.api.schemas import (
    DrawingIngestSummary,
    FileIngestOut,
    IngestOut,
    IngestRunOut,
    ModelIngestSummary,
    SheetIngestOut,
)
from app.geometry.errors import GeometryUnavailableError, ModelLimitError, UnreadableModelError
from app.ingestion.pdf import UnreadableDocumentError
from app.ingestion.readers import SUPPORTED_SUFFIXES, UnsupportedFileError
from app.repositories.parts import list_runs
from app.services.ingest_service import ingest_file_bytes

router = APIRouter(tags=["ingest"])


@router.post(
    "/ingest",
    response_model=IngestOut,
    summary="Upload and ingest spreadsheets, PDF drawings and IGES models",
)
def ingest(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    store: StoreDep,
    files: Annotated[
        list[UploadFile], File(description=".xlsx, .xls, .csv, .pdf, .igs or .iges files")
    ],
) -> IngestOut:
    out: list[FileIngestOut] = []
    limit = settings.max_upload_mb * 1024 * 1024
    for upload in files:
        name = (upload.filename or "upload").replace("\\", "/").rsplit("/", 1)[-1]
        if name.lower().endswith((".step", ".stp", ".p21")):
            raise ProblemError(
                415, "Unsupported file", f"{name}: STEP models are not supported yet; export IGES"
            )
        if not any(name.lower().endswith(s) for s in SUPPORTED_SUFFIXES):
            raise ProblemError(
                415, "Unsupported file", f"{name}: expected one of {sorted(SUPPORTED_SUFFIXES)}"
            )
        data = upload.file.read(limit + 1)
        if len(data) > limit:
            raise ProblemError(413, "File too large", f"{name} exceeds {settings.max_upload_mb} MB")
        try:
            outcome = ingest_file_bytes(
                session, data, name, store, settings.pdf_max_pages, request.app.state.geometry
            )
        except UnsupportedFileError as exc:
            raise ProblemError(415, "Unsupported file", str(exc)) from exc
        except UnreadableDocumentError as exc:
            raise ProblemError(422, "Unreadable document", f"{name}: {exc}") from exc
        except UnreadableModelError as exc:
            raise ProblemError(422, "Unreadable model", f"{name}: {exc}") from exc
        except ModelLimitError as exc:
            raise ProblemError(413, "Model too large", f"{name}: {exc}") from exc
        except GeometryUnavailableError as exc:
            raise ProblemError(503, "3D geometry kernel unavailable", str(exc)) from exc
        out.append(
            FileIngestOut(
                file_name=outcome.file_name,
                run_id=outcome.run_id,
                status=outcome.status,
                parts=outcome.parts,
                superseded_runs=outcome.superseded_runs,
                warnings=outcome.warnings,
                sheets=[SheetIngestOut(**s) for s in outcome.sheets],
                kind=outcome.kind,
                drawing=(
                    DrawingIngestSummary.model_validate(outcome.drawing)
                    if outcome.drawing
                    else None
                ),
                model=ModelIngestSummary.model_validate(outcome.model) if outcome.model else None,
            )
        )
    return IngestOut(files=out)


@router.get("/ingest/runs", response_model=list[IngestRunOut], summary="Ingest history")
def runs(session: SessionDep) -> list[IngestRunOut]:
    return [IngestRunOut.model_validate(r, from_attributes=True) for r in list_runs(session)]
