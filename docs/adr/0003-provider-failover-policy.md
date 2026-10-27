---
status: accepted
date: 2026-10-27
---

# 0003 Anthropic primary, Groq fallback, behind one gateway

## Context

The user chose Anthropic first and Groq as fallback. Groq retired its Llama models for
non-enterprise tiers in August 2026; `openai/gpt-oss-120b` is its production model with strict
`json_schema` output. The free tier allows roughly 8,000 tokens per minute.

## Decision

- One `LLMProvider` port; adapters for Anthropic (`claude-opus-5-5`, structured outputs via
  `messages.parse`, server-side refusal fallback `fallbacks="default"`), Groq (strict JSON
  schema generated from the same Pydantic model) and an offline rules engine.
- `FailoverGateway`: retry a transient error (timeout, connection, 429, 5xx, 529) once with
  jitter that honours `retry-after`, then fall back. Re-ask once on invalid output. Never fall
  back on 400/401/403/404: a misconfiguration is surfaced, not masked. A refusal becomes a
  "clarify" answer. A small circuit breaker skips a provider that keeps failing.
- Every attempt is logged to `llm_call` (provider, model, latency, tokens, cost, error) and the
  answer states which provider and model produced it.

## Consequences

The app keeps answering through an Anthropic outage, and judges can see when it did. Without
API keys the app runs on the offline engine, which keeps CI and demos keyless.
