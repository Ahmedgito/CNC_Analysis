"""PDF drawings: rendered pages for the viewer, consented scan reading, unlinked drawings."""

from __future__ import annotations

from typing import Annotated

from asgi_correlation_id.context import correlation_id
from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from app.api.deps import ProblemError, SessionDep, StoreDep
from app.api.schemas import PartOut
from app.domain.drawing import DrawingSlice
from app.domain.record import PartRecord
from app.llm.base import ProviderError
from app.repositories.parts import unlinked_drawings
from app.services.part_service import resolve_part
from app.services.vision_service import ScanNotFoundError, VisionService, VisionUnavailableError

router = APIRouter(tags=["drawings"])


def _record(session, part_number: str) -> PartRecord:
    res = resolve_part(session, part_number)
    if res.record is None:
        raise ProblemError(
            404,
            "Part not found",
            f"No part '{part_number}' in the ingested files.",
            suggestions=res.suggestions,
        )
    return res.record


def _drawing(record: PartRecord, file_name: str) -> DrawingSlice:
    drawing = next((d for d in record.drawings if d.file == file_name), None)
    if drawing is None:
        raise ProblemError(
            404,
            "Drawing not found",
            f"Part {record.display_part_number} has no drawing named '{file_name}'.",
        )
    return drawing


@router.get(
    "/parts/{part_number}/drawings/{file_name}/pages/{page}.png",
    summary="A drawing page rendered as PNG (cached)",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}, 404: {"description": "Unknown page"}},
)
def drawing_page(
    part_number: str,
    file_name: str,
    page: int,
    session: SessionDep,
    store: StoreDep,
    dpi: Annotated[int, Query(ge=36, le=200)] = 110,
) -> Response:
    drawing = _drawing(_record(session, part_number), file_name)
    if not 1 <= page <= drawing.page_count:
        raise ProblemError(404, "Page not found", f"{file_name} has {drawing.page_count} page(s).")
    correction = drawing.pages[page - 1].correction if page <= len(drawing.pages) else 0
    png = store.page_png(drawing.sha256, page, dpi, correction)
    if png is None:
        raise ProblemError(
            404,
            "Drawing file missing",
            f"The original bytes of {file_name} are not in the file store; re-ingest the file.",
        )
    etag = f'"{drawing.sha256[:16]}-p{page}-{dpi}-r{correction}"'
    return Response(
        png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=31536000, immutable", "ETag": etag},
    )


@router.post(
    "/parts/{part_number}/drawings/{file_name}/read-scan",
    response_model=PartOut,
    summary="Read a scanned drawing with the vision model (only on the user's request)",
    responses={
        404: {"description": "No scanned drawing with that name"},
        503: {"description": "No vision-capable model is configured"},
    },
)
async def read_scan(part_number: str, file_name: str, request: Request) -> PartOut:
    factory = request.app.state.session_factory

    def load() -> PartRecord:
        with factory() as session:
            return _record(session, part_number)

    record = await run_in_threadpool(load)
    _drawing(record, file_name)
    vision: VisionService = request.app.state.vision
    try:
        await vision.read_scan(record.part_key, file_name, correlation_id.get())
    except ScanNotFoundError as exc:
        raise ProblemError(404, "Scan not found", str(exc)) from exc
    except VisionUnavailableError as exc:
        raise ProblemError(503, "Vision model unavailable", str(exc)) from exc
    except ProviderError as exc:
        raise ProblemError(502, "Vision model failed", str(exc)) from exc
    return PartOut(record=await run_in_threadpool(load), related=[])


@router.get(
    "/drawings/unlinked",
    response_model=list[DrawingSlice],
    summary="Drawings whose part number could not be identified",
)
def unlinked(session: SessionDep) -> list[DrawingSlice]:
    return unlinked_drawings(session)
