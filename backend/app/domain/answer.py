"""The verified answer returned to clients (and stored with each assistant message)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, Field

from app.domain.drawing import CrossCheck
from app.domain.record import SourceKind, SourceStatus

AnswerStatus = Literal[
    "answered",  # stated directly in the record, with verified evidence
    "computed",  # derived by the compute engine from verified cells
    "not_found",  # the files do not contain it
    "clarify",  # question unclear, or it could not be computed safely
    "needs_consent",  # the answer needs a scanned drawing that has not been read yet
    "blocked",  # request conflicts with answering only from the files
    "part_not_found",  # unknown part number; no LLM call made
    "invalid_question",  # empty, too long, or unreadable; no LLM call made
    "error",  # every LLM provider failed
]


_FACT_ID = Field(validation_alias=AliasChoices("fact_id", "cell_id"))


class EvidenceOut(BaseModel):
    """One verified source fact behind an answer. Answers stored before Level 2 used ``cell_id``."""

    fact_id: str = _FACT_ID
    source: Literal["excel", "pdf"] = "excel"
    file: str
    locator: str = ""
    header: str = Field(description="Column header or drawing label as printed")
    canonical: str | None
    value: str
    quoted: str
    hidden: bool = False
    stale: bool = False
    confidence: Literal["exact", "inferred", "vision"] = "exact"
    auto_linked: bool = Field(
        default=False,
        description="Value appears verbatim in the answer but the model did not cite it",
    )
    # Excel provenance
    sheet: str | None = None
    cell: str | None = Field(default=None, description="Excel coordinate, e.g. C2")
    row: int | None = None
    # PDF provenance
    page: int | None = None
    region: str | None = None
    bbox: list[float] | None = None


class DroppedOut(BaseModel):
    fact_id: str = _FACT_ID
    quoted: str
    reason: str


class ComputationInputOut(BaseModel):
    name: str
    fact_id: str = _FACT_ID
    value: str = Field(validation_alias=AliasChoices("value", "cell_value"))
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


class AskAction(BaseModel):
    """Something the user can approve; the app never does it without a yes."""

    id: Literal["read_scan"]
    file: str
    label: str
    reply: str = Field(description="Message the client sends to approve, e.g. 'Yes, read it.'")


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
    cross_checks: list[CrossCheck] = Field(
        default_factory=list, description="Spreadsheet-vs-drawing comparisons the answer relates to"
    )
    actions: list[AskAction] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    request_id: str | None = None
    created_at: datetime | None = None


class StageEvent(BaseModel):
    stage: Literal[
        "validating",
        "loading_record",
        "reading_scan",
        "asking_llm",
        "verifying",
        "computing",
        "saving",
    ]
    detail: str | None = None
