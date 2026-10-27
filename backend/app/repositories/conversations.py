"""Conversations, messages and the LLM call log."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Conversation, LLMCall, Message
from app.llm.gateway import CallRecord
from app.llm.prompts import HistoryTurn


def get_or_create_conversation(
    session: Session, conversation_id: uuid.UUID | None, part_key: str
) -> Conversation:
    if conversation_id is not None:
        conv = session.get(Conversation, conversation_id)
        if conv is not None and conv.part_key == part_key:
            return conv
    conv = Conversation(part_key=part_key)
    session.add(conv)
    session.flush()
    return conv


def get_conversation(session: Session, conversation_id: uuid.UUID) -> Conversation | None:
    return session.get(Conversation, conversation_id)


def recent_history(session: Session, conversation_id: uuid.UUID, turns: int) -> list[HistoryTurn]:
    msgs = list(
        session.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(turns * 2)
        )
    )[::-1]
    history: list[HistoryTurn] = []
    pending_q: str | None = None
    for m in msgs:
        if m.role == "user":
            pending_q = m.content
        elif m.role == "assistant" and pending_q is not None:
            status = (m.answer or {}).get("status", "answered")
            history.append(HistoryTurn(question=pending_q, answer=m.content, status=status))
            pending_q = None
    return history[-turns:]


def save_exchange(
    session: Session, conversation_id: uuid.UUID, question: str, answer_text: str, answer: dict
) -> uuid.UUID:
    session.add(Message(conversation_id=conversation_id, role="user", content=question))
    session.flush()
    assistant = Message(
        conversation_id=conversation_id, role="assistant", content=answer_text, answer=answer
    )
    session.add(assistant)
    session.flush()
    return assistant.id


def _cost(record: CallRecord, prices: dict[str, tuple[float, float]]) -> Decimal | None:
    price = prices.get(record.model)
    if price is None or record.usage.input_tokens is None:
        return None
    usd = (
        record.usage.input_tokens * price[0] + (record.usage.output_tokens or 0) * price[1]
    ) / 1e6
    return Decimal(f"{usd:.6f}")


def save_llm_calls(
    session: Session,
    calls: list[CallRecord],
    *,
    request_id: str | None,
    conversation_id: uuid.UUID | None,
    part_key: str | None,
    prompt_sha256: str | None,
    prices: dict[str, tuple[float, float]],
    fallback_reason: str | None,
) -> None:
    for c in calls:
        session.add(
            LLMCall(
                request_id=request_id,
                conversation_id=conversation_id,
                part_key=part_key,
                provider=c.provider,
                model=c.model,
                attempt=c.attempt,
                fallback_reason=fallback_reason,
                prompt_sha256=prompt_sha256,
                input_tokens=c.usage.input_tokens,
                output_tokens=c.usage.output_tokens,
                cached_tokens=c.usage.cached_tokens,
                latency_ms=c.latency_ms,
                cost_usd=_cost(c, prices),
                status=c.status,
                error=c.error,
            )
        )
    session.flush()


def recent_calls(session: Session, limit: int = 50) -> list[LLMCall]:
    return list(session.scalars(select(LLMCall).order_by(LLMCall.created_at.desc()).limit(limit)))
