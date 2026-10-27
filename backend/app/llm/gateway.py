"""Provider failover: retry transient errors once, then fall back; never mask permanent errors.

Policy (see docs/adr/0005):
- Transient (timeout, connection, 429, 5xx, overloaded): one retry on the same provider with
  jittered backoff that honours ``retry-after``, then the next provider.
- Invalid output (schema failure): one re-ask on the same provider with the error appended,
  then the next provider.
- Refusal: returned as a ``clarify`` draft; not retried elsewhere (Anthropic's server-side
  refusal fallback has already run inside the call).
- Permanent (auth, bad request): raised immediately. Masking a misconfiguration with a
  fallback would hide a bug.
A small circuit breaker skips a provider after repeated transient failures for a cool-down.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field, replace

from app.llm.base import (
    InvalidOutputError,
    LLMProvider,
    PermanentProviderError,
    Prompt,
    ProviderResult,
    RefusalError,
    TransientProviderError,
    Usage,
)
from app.llm.schemas import AnswerDraft
from app.logging_setup import log

MAX_BACKOFF_S = 8.0


@dataclass(slots=True)
class CallRecord:
    provider: str
    model: str
    attempt: int
    status: str  # ok | transient_error | invalid_output | refusal | permanent_error | skipped
    latency_ms: int
    usage: Usage = field(default_factory=Usage)
    error: str | None = None


@dataclass(slots=True)
class GatewayResult:
    draft: AnswerDraft
    provider: str
    model: str
    calls: list[CallRecord]
    fallback_used: bool
    fallback_reason: str | None
    served_by_refusal_fallback: bool = False


class AllProvidersFailedError(Exception):
    def __init__(self, message: str, calls: list[CallRecord]) -> None:
        super().__init__(message)
        self.calls = calls


class ProviderConfigError(Exception):
    def __init__(self, message: str, calls: list[CallRecord]) -> None:
        super().__init__(message)
        self.calls = calls


class CircuitBreaker:
    def __init__(self, fail_max: int = 3, reset_s: float = 60.0) -> None:
        self.fail_max, self.reset_s = fail_max, reset_s
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at >= self.reset_s:
            self._opened_at, self._failures = None, self.fail_max - 1  # half-open: one try
            return False
        return True

    def success(self) -> None:
        self._failures, self._opened_at = 0, None

    def failure(self) -> None:
        self._failures += 1
        if self._failures >= self.fail_max:
            self._opened_at = time.monotonic()


def _refusal_draft() -> AnswerDraft:
    return AnswerDraft(
        status="clarify",
        answer=(
            "I can't answer that request as phrased. Please rephrase it as a question about the "
            "part's manufacturing record."
        ),
        evidence=[],
        computation=None,
        general_knowledge=[],
        missing_information=[],
        confidence="low",
        reason="the model declined the request",
    )


class FailoverGateway:
    def __init__(
        self,
        providers: list[LLMProvider],
        breaker_fail_max: int = 3,
        breaker_reset_s: float = 60.0,
        sleep=asyncio.sleep,
    ) -> None:
        if not providers:
            raise ValueError("at least one LLM provider is required")
        self.providers = providers
        self._breakers = {
            p.name: CircuitBreaker(breaker_fail_max, breaker_reset_s) for p in providers
        }
        self._sleep = sleep

    @property
    def primary(self) -> LLMProvider:
        return self.providers[0]

    async def answer(self, prompt: Prompt) -> GatewayResult:
        calls: list[CallRecord] = []
        reasons: list[str] = []
        for index, provider in enumerate(self.providers):
            breaker = self._breakers[provider.name]
            if breaker.is_open and index < len(self.providers) - 1:
                calls.append(
                    CallRecord(provider.name, provider.model, 0, "skipped", 0, error="circuit open")
                )
                reasons.append(f"{provider.name}: circuit open")
                continue
            current = prompt
            for attempt in (1, 2):
                started = time.perf_counter()
                try:
                    result: ProviderResult = await provider.answer(current)
                except TransientProviderError as exc:
                    calls.append(self._rec(provider, attempt, "transient_error", started, str(exc)))
                    breaker.failure()
                    reasons.append(f"{provider.name}: {exc}")
                    log.warning(
                        "llm.transient", provider=provider.name, attempt=attempt, error=str(exc)
                    )
                    if attempt == 1 and not breaker.is_open:
                        await self._sleep(self._backoff(exc.retry_after_s))
                        continue
                    break
                except InvalidOutputError as exc:
                    calls.append(self._rec(provider, attempt, "invalid_output", started, str(exc)))
                    reasons.append(f"{provider.name}: invalid output")
                    log.warning(
                        "llm.invalid_output",
                        provider=provider.name,
                        attempt=attempt,
                        error=str(exc),
                    )
                    if attempt == 1:
                        current = replace(
                            prompt,
                            user=prompt.user
                            + "\n<system_notes>\n  - Your previous reply was rejected: "
                            + str(exc)[:500]
                            + ". Return JSON that matches the schema exactly.\n</system_notes>",
                        )
                        continue
                    break
                except RefusalError as exc:
                    calls.append(self._rec(provider, attempt, "refusal", started, str(exc)))
                    return GatewayResult(
                        draft=_refusal_draft(),
                        provider=provider.name,
                        model=provider.model,
                        calls=calls,
                        fallback_used=index > 0,
                        fallback_reason="; ".join(reasons) or None,
                    )
                except PermanentProviderError as exc:
                    calls.append(self._rec(provider, attempt, "permanent_error", started, str(exc)))
                    log.error("llm.permanent", provider=provider.name, error=str(exc))
                    raise ProviderConfigError(str(exc), calls) from exc

                breaker.success()
                rec = self._rec(provider, attempt, "ok", started, None)
                rec.model, rec.usage = result.model, result.usage
                calls.append(rec)
                return GatewayResult(
                    draft=result.draft,
                    provider=provider.name,
                    model=result.model,
                    calls=calls,
                    fallback_used=index > 0,
                    fallback_reason="; ".join(reasons) if index > 0 else None,
                    served_by_refusal_fallback=result.served_by_fallback_model,
                )
        raise AllProvidersFailedError("; ".join(reasons) or "no provider available", calls)

    @staticmethod
    def _backoff(retry_after_s: float | None) -> float:
        if retry_after_s is not None:
            return min(retry_after_s, MAX_BACKOFF_S)
        return random.uniform(0.5, 1.5)  # noqa: S311 - jitter, not crypto

    @staticmethod
    def _rec(
        provider: LLMProvider, attempt: int, status: str, started: float, error: str | None
    ) -> CallRecord:
        return CallRecord(
            provider=provider.name,
            model=provider.model,
            attempt=attempt,
            status=status,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=error,
        )


def build_gateway(settings) -> FailoverGateway:
    """Construct providers from settings. Providers without a key are skipped (and logged)."""
    from app.llm.fake_adapter import FakeProvider

    providers: list[LLMProvider] = []
    for name in (settings.llm_primary_provider, settings.llm_fallback_provider):
        if name == "anthropic":
            key, token = settings.anthropic_api_key, settings.anthropic_auth_token
            if key is None and token is None:
                log.warning(
                    "llm.provider_skipped",
                    provider="anthropic",
                    reason="neither ANTHROPIC_API_KEY nor ANTHROPIC_AUTH_TOKEN is set",
                )
                continue
            from app.llm.anthropic_adapter import AnthropicProvider

            providers.append(
                AnthropicProvider(
                    key.get_secret_value() if key else None,
                    settings.anthropic_model,
                    settings.llm_effort,
                    settings.llm_max_tokens,
                    settings.llm_timeout_s,
                    auth_token=token.get_secret_value() if token else None,
                )
            )
        elif name == "claude_code":
            if settings.claude_code_oauth_token is None:
                log.warning(
                    "llm.provider_skipped",
                    provider="claude_code",
                    reason="CLAUDE_CODE_OAUTH_TOKEN not set",
                )
                continue
            from app.llm.claude_code_adapter import (
                ClaudeCodeNotInstalledError,
                ClaudeCodeProvider,
                resolve_binary,
            )

            try:
                binary = resolve_binary(settings.claude_code_bin)
            except ClaudeCodeNotInstalledError as exc:
                log.warning("llm.provider_skipped", provider="claude_code", reason=str(exc))
                continue
            providers.append(
                ClaudeCodeProvider(
                    settings.claude_code_oauth_token.get_secret_value(),
                    settings.claude_code_model,
                    binary,
                    settings.claude_code_timeout_s,
                )
            )
        elif name == "groq":
            if settings.groq_api_key is None:
                log.warning("llm.provider_skipped", provider="groq", reason="GROQ_API_KEY not set")
                continue
            from app.llm.groq_adapter import GroqProvider

            providers.append(
                GroqProvider(
                    settings.groq_api_key.get_secret_value(),
                    settings.groq_model,
                    settings.llm_max_tokens,
                    settings.llm_timeout_s,
                )
            )
        elif name == "fake":
            providers.append(FakeProvider())
    if not providers:
        log.warning("llm.no_providers", detail="no API keys configured; using offline rules engine")
        providers.append(FakeProvider())
    return FailoverGateway(providers, settings.breaker_fail_max, settings.breaker_reset_s)
