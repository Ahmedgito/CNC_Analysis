from __future__ import annotations

import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import ProblemError, SessionDep, StoreDep
from app.api.schemas import PartListOut, PartOut
from app.domain.answer import AskResult
from app.domain.record import PartRecord
from app.repositories.conversations import get_conversation
from app.repositories.parts import list_parts, suggest_parts
from app.services.part_service import resolve_part
from app.services.report import build_report

router = APIRouter(prefix="/parts", tags=["parts"])


@router.get("", response_model=PartListOut, summary="List or search parts")
def get_parts(
    session: SessionDep,
    q: str | None = Query(
        default=None, max_length=64, description="Part number or description text"
    ),
) -> PartListOut:
    parts = list_parts(session, q)
    return PartListOut(parts=parts, total=len(parts))


def _resolve(session: Session, part_number: str) -> PartRecord:
    res = resolve_part(session, part_number)
    if not res.found or res.record is None:
        raise ProblemError(
            404,
            "Part not found",
            f"No part '{part_number}' in the ingested files.",
            part_number=part_number,
            suggestions=res.suggestions,
        )
    return res.record


def _related(session: Session, record: PartRecord) -> list[str]:
    return [k for k in suggest_parts(session, record.part_key) if k.startswith(record.base_key)]


@router.get(
    "/{part_number}",
    response_model=PartOut,
    summary="Full manufacturing record for one part",
    responses={404: {"description": "Unknown part; body lists suggestions"}},
)
def get_part_record(part_number: str, session: SessionDep) -> PartOut:
    record = _resolve(session, part_number)
    return PartOut(record=record, related=_related(session, record))


@router.get(
    "/{part_number}/report.pdf",
    summary="The part report as PDF: sources, cross-check, record, drawings, models",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}},
        404: {"description": "Unknown part, or a conversation that is not about this part"},
    },
)
def part_report(
    part_number: str,
    session: SessionDep,
    store: StoreDep,
    conversation: Annotated[
        uuid.UUID | None,
        Query(description="Include this conversation's questions and verified answers"),
    ] = None,
) -> Response:
    record = _resolve(session, part_number)
    answers: list[AskResult] = []
    if conversation is not None:
        conv = get_conversation(session, conversation)
        if conv is None or conv.part_key != record.part_key:
            raise ProblemError(
                404,
                "Conversation not found",
                f"No conversation {conversation} about part {record.display_part_number}.",
            )
        answers = [
            AskResult.model_validate(m.answer)
            for m in conv.messages
            if m.role == "assistant" and m.answer
        ]
    pdf = build_report(record, store, related=_related(session, record), answers=answers)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", record.display_part_number).strip("_") or "part"
    return Response(
        pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="part-{safe}-report.pdf"',
            "Cache-Control": "no-store",
        },
    )
