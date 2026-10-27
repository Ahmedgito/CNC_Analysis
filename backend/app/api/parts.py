from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import ProblemError, SessionDep
from app.api.schemas import PartListOut, PartOut
from app.repositories.parts import list_parts, suggest_parts
from app.services.part_service import resolve_part

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


@router.get(
    "/{part_number}",
    response_model=PartOut,
    summary="Full manufacturing record for one part",
    responses={404: {"description": "Unknown part; body lists suggestions"}},
)
def get_part_record(part_number: str, session: SessionDep) -> PartOut:
    res = resolve_part(session, part_number)
    if not res.found or res.record is None:
        raise ProblemError(
            404,
            "Part not found",
            f"No part '{part_number}' in the ingested files.",
            part_number=part_number,
            suggestions=res.suggestions,
        )
    related = [
        k for k in suggest_parts(session, res.record.part_key) if k.startswith(res.record.base_key)
    ]
    return PartOut(record=res.record, related=related)
