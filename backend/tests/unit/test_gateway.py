from __future__ import annotations

import pytest

from app.llm.base import (
    InvalidOutputError,
    PermanentProviderError,
    Prompt,
    ProviderResult,
    RefusalError,
    TransientProviderError,
)
from app.llm.gateway import AllProvidersFailedError, FailoverGateway, ProviderConfigError
from app.llm.schemas import AnswerDraft, strict_json_schema

PROMPT = Prompt(system="s", user="u", prompt_sha256="x")


def _draft(text: str = "ok") -> AnswerDraft:
    return AnswerDraft(
        status="answered",
        answer=text,
        evidence=[],
        computation=None,
        general_knowledge=[],
        missing_information=[],
        confidence="high",
        reason="r",
    )


class Scripted:
    """Provider that replays a script of exceptions / answers."""

    def __init__(self, name: str, script: list) -> None:
        self.name, self.model, self.script, self.calls = name, f"{name}-model", list(script), 0

    async def answer(self, prompt: Prompt) -> ProviderResult:
        self.calls += 1
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return ProviderResult(draft=_draft(step), model=self.model)


async def _nosleep(_: float) -> None:
    return None


async def test_primary_success():
    p = Scripted("primary", ["hello"])
    r = await FailoverGateway([p], sleep=_nosleep).answer(PROMPT)
    assert r.provider == "primary" and not r.fallback_used and r.draft.answer == "hello"


async def test_transient_retried_once_then_succeeds():
    p = Scripted("primary", [TransientProviderError("429"), "second try"])
    r = await FailoverGateway([p], sleep=_nosleep).answer(PROMPT)
    assert r.draft.answer == "second try" and p.calls == 2
    assert [c.status for c in r.calls] == ["transient_error", "ok"]


async def test_falls_back_after_two_transient_failures():
    p = Scripted("anthropic", [TransientProviderError("529"), TransientProviderError("529")])
    f = Scripted("groq", ["from groq"])
    r = await FailoverGateway([p, f], sleep=_nosleep).answer(PROMPT)
    assert r.provider == "groq" and r.fallback_used and "529" in (r.fallback_reason or "")


async def test_permanent_error_is_not_masked_by_fallback():
    p = Scripted("anthropic", [PermanentProviderError("401 invalid key")])
    f = Scripted("groq", ["should not be used"])
    with pytest.raises(ProviderConfigError):
        await FailoverGateway([p, f], sleep=_nosleep).answer(PROMPT)
    assert f.calls == 0


async def test_refusal_becomes_clarify_without_fallback():
    p = Scripted("anthropic", [RefusalError("declined")])
    f = Scripted("groq", ["nope"])
    r = await FailoverGateway([p, f], sleep=_nosleep).answer(PROMPT)
    assert r.draft.status == "clarify" and f.calls == 0


async def test_invalid_output_reasked_with_feedback():
    seen: list[str] = []

    class Picky(Scripted):
        async def answer(self, prompt: Prompt) -> ProviderResult:
            seen.append(prompt.user)
            return await super().answer(prompt)

    p = Picky("anthropic", [InvalidOutputError("missing field"), "fixed"])
    r = await FailoverGateway([p], sleep=_nosleep).answer(PROMPT)
    assert r.draft.answer == "fixed"
    assert "previous reply was rejected" in seen[1]


async def test_all_fail():
    p = Scripted("a", [TransientProviderError("x"), TransientProviderError("x")])
    f = Scripted("b", [TransientProviderError("y"), TransientProviderError("y")])
    with pytest.raises(AllProvidersFailedError) as exc:
        await FailoverGateway([p, f], sleep=_nosleep).answer(PROMPT)
    assert len(exc.value.calls) == 4


async def test_circuit_breaker_skips_failing_primary():
    p = Scripted("a", [TransientProviderError("x")] * 3)
    f = Scripted("b", ["b1", "b2"])
    gw = FailoverGateway([p, f], breaker_fail_max=2, breaker_reset_s=60, sleep=_nosleep)
    first = await gw.answer(PROMPT)  # two failures open the breaker
    second = await gw.answer(PROMPT)
    assert first.provider == second.provider == "b"
    assert p.calls == 2
    assert second.calls[0].status == "skipped"


def test_strict_schema_requires_every_property():
    schema = strict_json_schema(AnswerDraft)

    def objects(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                yield node
            for v in node.values():
                yield from objects(v)
        elif isinstance(node, list):
            for v in node:
                yield from objects(v)

    found = list(objects(schema))
    assert len(found) >= 4
    for obj in found:
        assert obj["additionalProperties"] is False
        assert set(obj["required"]) == set(obj["properties"])
    assert "default" not in str(schema)
