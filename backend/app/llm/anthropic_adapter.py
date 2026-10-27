"""Anthropic Claude adapter (primary provider).

Uses structured outputs via ``client.beta.messages.parse(output_format=AnswerDraft)`` so the
response is schema-valid JSON, plus the server-side refusal fallback (``fallbacks="default"``)
so a safety-classifier decline is retried on a substitute model inside the same call. SDK
retries are disabled; the gateway owns the retry and failover policy.
"""

from __future__ import annotations

import anthropic
from pydantic import ValidationError

from app.llm.base import (
    InvalidOutputError,
    PermanentProviderError,
    Prompt,
    ProviderResult,
    RefusalError,
    TransientProviderError,
    Usage,
)
from app.llm.schemas import AnswerDraft

REFUSAL_FALLBACK_BETA = "server-side-fallback-2026-07-01"
OAUTH_BETA = "oauth-2025-04-20"


def _retry_after(exc: anthropic.APIStatusError) -> float | None:
    try:
        return float(exc.response.headers.get("retry-after", ""))
    except (TypeError, ValueError):
        return None


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        api_key: str | None,
        model: str,
        effort: str = "medium",
        max_tokens: int = 4096,
        timeout_s: float = 45.0,
        auth_token: str | None = None,
    ) -> None:
        self.model = model
        self._effort = effort
        self._max_tokens = max_tokens
        self._betas = [REFUSAL_FALLBACK_BETA]
        if api_key:
            self._client = anthropic.AsyncAnthropic(
                api_key=api_key, timeout=timeout_s, max_retries=0
            )
        elif auth_token:
            # OAuth bearer token: sent as Authorization: Bearer with the documented OAuth beta.
            self._client = anthropic.AsyncAnthropic(
                auth_token=auth_token, timeout=timeout_s, max_retries=0
            )
            self._betas.append(OAUTH_BETA)
        else:
            raise ValueError("AnthropicProvider needs an API key or an auth token")

    async def answer(self, prompt: Prompt) -> ProviderResult:
        try:
            resp = await self._client.beta.messages.parse(
                model=self.model,
                max_tokens=self._max_tokens,
                system=[
                    {"type": "text", "text": prompt.system, "cache_control": {"type": "ephemeral"}}
                ],
                messages=[{"role": "user", "content": prompt.user}],
                output_format=AnswerDraft,
                output_config={"effort": self._effort},  # type: ignore[typeddict-item]
                betas=self._betas,  # type: ignore[arg-type]
                fallbacks="default",
            )
        except anthropic.RateLimitError as exc:
            raise TransientProviderError(
                f"anthropic 429: {exc.message}", _retry_after(exc)
            ) from exc
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise PermanentProviderError(f"anthropic auth: {exc.message}") from exc
        except (anthropic.BadRequestError, anthropic.NotFoundError) as exc:
            raise PermanentProviderError(f"anthropic request rejected: {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500 or exc.status_code in (408, 409):
                raise TransientProviderError(
                    f"anthropic {exc.status_code}: {exc.message}", _retry_after(exc)
                ) from exc
            raise PermanentProviderError(f"anthropic {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:  # includes APITimeoutError
            raise TransientProviderError(f"anthropic connection: {exc}") from exc
        except ValidationError as exc:
            raise InvalidOutputError(f"anthropic output failed validation: {exc}") from exc

        if resp.stop_reason == "refusal":
            raise RefusalError("the model declined to answer this request")
        if resp.stop_reason == "max_tokens":
            raise InvalidOutputError("anthropic output truncated at max_tokens")
        draft = resp.parsed_output
        if draft is None:
            raise InvalidOutputError("anthropic returned no parsable structured output")

        usage = resp.usage
        fallback_ran = any(
            getattr(entry, "type", None) == "fallback_message"
            for entry in (getattr(usage, "iterations", None) or [])
        )
        return ProviderResult(
            draft=draft,
            model=resp.model,
            usage=Usage(
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cached_tokens=usage.cache_read_input_tokens,
            ),
            served_by_fallback_model=fallback_ran,
        )
