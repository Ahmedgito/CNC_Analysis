"""The verified answer returned to clients (and stored with each assistant message)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.record import SourceKind, SourceStatus

AnswerStatus = Literal[
    "answered",  # stated directly in the record, with verified evidence
    "computed",  # derived by the compute engine from verified cells
    "not_found",  # the files do not contain it
    "clarify",  # question unclear, or it could not be computed safely
    "blocked",  # request conflicts with answering only from the files
    "part_not_found",  # unknown part number; no LLM call made
    "invalid_question",  # empty, too long, or unreadable; no LLM call made
    "error",  # every LLM provider failed
]


class EvidenceOut(BaseModel):
    cell_id: str
    file: str
    sheet: str
    cell: str = Field(description="Excel coordinate, e.g. C2")
    row: int
    header: str
    canonical: str | None
    value: str
    quoted: str
    hidden: bool = False
    auto_linked: bool = Field(
        default=False,
        description="Value appears verbatim in the answer but the model did not cite it",
    )


class DroppedOut(BaseModel):
    cell_id: str
    quoted: str
    reason: str


class ComputationInputOut(BaseModel):
    name: str
    cell_id: str
    cell_value: str
    number: float


class ComputationOut(BaseModel):
    label: str
    expression: str
    working: str
    result: float
    display: str
    unit: str | None
    inputs: list[ComputationInputOut]
    constants: list[float] = Field(default_factory=list)


class VerificationOut(BaseModel):
    citations_checked: int
    citations_verified: int
    auto_linked: int
    dropped: list[DroppedOut] = Field(default_factory=list)
    unsupported_numbers: list[str] = Field(default_factory=list)


class ProviderOut(BaseModel):
    provider: str
    model: str
    fallback_used: bool = False
    fallback_reason: str | None = None
    refusal_fallback_used: bool = False
    attempts: int = 0
    latency_ms: int = 0


class AskResult(BaseModel):
    message_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    part_number: str
    question: str
    status: AnswerStatus
    answer: str
    evidence: list[EvidenceOut] = Field(default_factory=list)
    computation: ComputationOut | None = None
    general_knowledge: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    available_fields: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "low"
    verification: VerificationOut | None = None
    provider: ProviderOut | None = None
    sources: dict[SourceKind, SourceStatus] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    request_id: str | None = None
    created_at: datetime | None = None


class StageEvent(BaseModel):
    stage: Literal["validating", "loading_record", "asking_llm", "verifying", "computing", "saving"]
    detail: str | None = None
