from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select, text

from app.api.deps import SessionDep, SettingsDep
from app.api.schemas import HealthOut, ReadyOut
from app.db.models import PartRow

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthOut, summary="Liveness (no dependencies)")
def healthz() -> HealthOut:
    return HealthOut(status="ok")


@router.get("/readyz", response_model=ReadyOut, summary="Readiness: database and provider keys")
def readyz(session: SessionDep, settings: SettingsDep) -> ReadyOut:
    session.execute(text("SELECT 1"))
    parts = session.scalar(select(func.count()).select_from(PartRow)) or 0
    return ReadyOut(
        status="ok",
        database=True,
        parts=parts,
        providers={
            "anthropic_key": settings.anthropic_api_key is not None
            or settings.anthropic_auth_token is not None,
            "claude_code_token": settings.claude_code_oauth_token is not None,
            "groq_key": settings.groq_api_key is not None,
        },
    )
