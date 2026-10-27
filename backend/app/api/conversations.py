from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.deps import ProblemError, SessionDep
from app.domain.answer import AskResult
from app.repositories.conversations import get_conversation, recent_calls

router = APIRouter(tags=["conversations"])


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    answer: AskResult | None
    created_at: datetime


class ConversationOut(BaseModel):
    id: uuid.UUID
    part_key: str
    created_at: datetime
    messages: list[MessageOut]


class LLMCallOut(BaseModel):
    id: uuid.UUID
    request_id: str | None
    part_key: str | None
    provider: str
    model: str
    attempt: int
    status: str
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    cost_usd: Decimal | None
    fallback_reason: str | None
    error: str | None
    created_at: datetime


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
def conversation(conversation_id: uuid.UUID, session: SessionDep) -> ConversationOut:
    conv = get_conversation(session, conversation_id)
    if conv is None:
        raise ProblemError(404, "Conversation not found", f"No conversation {conversation_id}")
    return ConversationOut(
        id=conv.id,
        part_key=conv.part_key,
        created_at=conv.created_at,
        messages=[
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                answer=AskResult.model_validate(m.answer) if m.answer else None,
                created_at=m.created_at,
            )
            for m in conv.messages
        ],
    )


@router.get(
    "/admin/llm-calls",
    response_model=list[LLMCallOut],
    tags=["admin"],
    summary="Recent LLM calls: provider, latency, tokens, cost",
)
def llm_calls(session: SessionDep, limit: int = Query(50, ge=1, le=500)) -> list[LLMCallOut]:
    return [
        LLMCallOut.model_validate(c, from_attributes=True) for c in recent_calls(session, limit)
    ]
