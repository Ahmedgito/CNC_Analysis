"""SQLAlchemy ORM models.

``cell`` is the audit trail: every citation an answer makes joins back to one row here.
``part_fragment`` stores one file's contribution to a part; ``part`` holds the merged record that
the LLM and UI read. Re-ingesting a changed file supersedes its old run and rebuilds the affected
parts, keeping old cells for audit.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("uuidv7()"))


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class IngestRun(Base):
    __tablename__ = "ingest_run"

    id: Mapped[uuid.UUID] = _uuid_pk()
    file_name: Mapped[str] = mapped_column(String(255), index=True)
    file_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    file_format: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | superseded
    part_count: Mapped[int] = mapped_column(Integer, default=0)
    cell_count: Mapped[int] = mapped_column(Integer, default=0)
    sheets: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = _created_at()

    fragments: Mapped[list[PartFragmentRow]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class CellRow(Base):
    __tablename__ = "cell"
    __table_args__ = (
        UniqueConstraint("run_id", "cell_id"),
        Index("ix_cell_text_search", "text_search", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingest_run.id", ondelete="CASCADE"), index=True
    )
    cell_id: Mapped[str] = mapped_column(String(512))
    part_key: Mapped[str | None] = mapped_column(String(64), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    sheet: Mapped[str] = mapped_column(String(255))
    row_num: Mapped[int] = mapped_column(Integer)
    col: Mapped[str] = mapped_column(String(8))
    header: Mapped[str] = mapped_column(Text)
    canonical: Mapped[str | None] = mapped_column(String(64))
    unit: Mapped[str | None] = mapped_column(String(16))
    value: Mapped[str] = mapped_column(Text)
    value_type: Mapped[str] = mapped_column(String(16))
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    comment: Mapped[str | None] = mapped_column(Text)
    formula: Mapped[str | None] = mapped_column(Text)
    text_search: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple', coalesce(header, '') || ' ' || coalesce(value, ''))",
            persisted=True,
        ),
    )


class PartFragmentRow(Base):
    __tablename__ = "part_fragment"
    __table_args__ = (UniqueConstraint("run_id", "part_key"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ingest_run.id", ondelete="CASCADE"), index=True
    )
    part_key: Mapped[str] = mapped_column(String(64), index=True)
    display_part_number: Mapped[str] = mapped_column(String(64))
    sheets: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)

    run: Mapped[IngestRun] = relationship(back_populates="fragments")


class PartRow(Base):
    __tablename__ = "part"
    __table_args__ = (Index("ix_part_record", "record", postgresql_using="gin"),)

    part_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_part_number: Mapped[str] = mapped_column(String(64))
    base_key: Mapped[str] = mapped_column(String(64), index=True)
    suffix: Mapped[str | None] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(Text)
    record: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Conversation(Base):
    __tablename__ = "conversation"

    id: Mapped[uuid.UUID] = _uuid_pk()
    part_key: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = _created_at()

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "message"

    id: Mapped[uuid.UUID] = _uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    answer: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class LLMCall(Base):
    __tablename__ = "llm_call"

    id: Mapped[uuid.UUID] = _uuid_pk()
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    part_key: Mapped[str | None] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    fallback_reason: Mapped[str | None] = mapped_column(Text)
    prompt_sha256: Mapped[str | None] = mapped_column(String(64))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cached_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    status: Mapped[str] = mapped_column(String(32))  # ok | error | refusal | invalid_output
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
