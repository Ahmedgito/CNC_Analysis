"""Provider port: the interface every LLM adapter implements, plus normalised errors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.llm.schemas import AnswerDraft


@dataclass(frozen=True, slots=True)
class Prompt:
    system: str
    user: str
    prompt_sha256: str


@dataclass(slots=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_tokens: int | None = None


@dataclass(slots=True)
class ProviderResult:
    draft: AnswerDraft
    model: str
    usage: Usage = field(default_factory=Usage)
    served_by_fallback_model: bool = False  # Anthropic server-side refusal fallback ran


class LLMProvider(Protocol):
    name: str
    model: str

    async def answer(self, prompt: Prompt) -> ProviderResult: ...


class ProviderError(Exception):
    """Base for normalised provider failures."""


class TransientProviderError(ProviderError):
    """Timeouts, connection failures, 429, 5xx, overloaded: retry, then fail over."""

    def __init__(self, message: str, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


class PermanentProviderError(ProviderError):
    """Bad request, auth, permission, not found: a bug or misconfiguration. Never masked."""


class InvalidOutputError(ProviderError):
    """The provider answered but the output does not satisfy the schema."""


class RefusalError(ProviderError):
    """The model (and any server-side fallback) declined to answer."""
