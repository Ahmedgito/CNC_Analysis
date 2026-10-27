"""Groq adapter (fallback provider), strict ``json_schema`` structured output.

Groq's strict mode requires every property in ``required`` and ``additionalProperties: false``
on every object; ``strict_json_schema`` produces that from the same Pydantic model the Anthropic
adapter uses, so both providers return an identical contract.
"""

from __future__ import annotations

import groq
from pydantic import ValidationError

from app.llm.base import (
    InvalidOutputError,
    PermanentProviderError,
    Prompt,
    ProviderResult,
    TransientProviderError,
    Usage,
)
from app.llm.schemas import AnswerDraft, strict_json_schema

_SCHEMA = strict_json_schema(AnswerDraft)


def _retry_after(exc: groq.APIStatusError) -> float | None:
    try:
        return float(exc.response.headers.get("retry-after", ""))
    except (TypeError, ValueError):
        return None


class GroqProvider:
    name = "groq"

    def __init__(
        self, api_key: str, model: str, max_tokens: int = 4096, timeout_s: float = 45.0
    ) -> None:
        self.model = model
        self._max_tokens = max_tokens
        self._client = groq.AsyncGroq(api_key=api_key, timeout=timeout_s, max_retries=0)

    async def answer(self, prompt: Prompt) -> ProviderResult:
        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": prompt.system},
                    {"role": "user", "content": prompt.user},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "answer_draft", "strict": True, "schema": _SCHEMA},
                },
                max_completion_tokens=self._max_tokens,
            )
        except groq.RateLimitError as exc:
            raise TransientProviderError(f"groq 429: {exc.message}", _retry_after(exc)) from exc
        except (groq.AuthenticationError, groq.PermissionDeniedError) as exc:
            raise PermanentProviderError(f"groq auth: {exc.message}") from exc
        except groq.BadRequestError as exc:
            # Groq reports schema-constrained generation failures as 400s.
            if "json" in str(exc.message).lower() or "schema" in str(exc.message).lower():
                raise InvalidOutputError(f"groq output failed schema: {exc.message}") from exc
            raise PermanentProviderError(f"groq request rejected: {exc.message}") from exc
        except groq.APIStatusError as exc:
            if exc.status_code >= 500 or exc.status_code in (408, 409, 498):
                raise TransientProviderError(
                    f"groq {exc.status_code}: {exc.message}", _retry_after(exc)
                ) from exc
            raise PermanentProviderError(f"groq {exc.status_code}: {exc.message}") from exc
        except groq.APIConnectionError as exc:  # includes APITimeoutError
            raise TransientProviderError(f"groq connection: {exc}") from exc

        choice = resp.choices[0]
        if choice.finish_reason == "length":
            raise InvalidOutputError("groq output truncated at max tokens")
        content = choice.message.content or ""
        try:
            draft = AnswerDraft.model_validate_json(content)
        except ValidationError as exc:
            raise InvalidOutputError(f"groq output failed validation: {exc}") from exc
        usage = resp.usage
        return ProviderResult(
            draft=draft,
            model=resp.model,
            usage=Usage(
                input_tokens=usage.prompt_tokens if usage else None,
                output_tokens=usage.completion_tokens if usage else None,
            ),
        )
