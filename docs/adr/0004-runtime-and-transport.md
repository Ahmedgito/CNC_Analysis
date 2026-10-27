---
status: accepted
date: 2026-10-27
---

# 0004 Sync database sessions, SSE progress stages, same-origin proxy

## Context

psycopg 3's async mode does not run on Windows' default (Proactor) event loop, which uvicorn
and pytest use there. Answers must be verified before any claim is shown, and Groq cannot
stream a schema-constrained answer. Next.js `rewrites()` buffer `text/event-stream`.

## Decision

- SQLAlchemy 2 with psycopg 3 in sync mode; FastAPI runs DB work in its threadpool. Async is
  used only for LLM network calls. One driver serves the API, CLI, Alembic and tests.
- `POST /parts/{pn}/ask` streams Server-Sent Events: `stage` events (validating, loading,
  asking, verifying, computing, saving), then one `answer` event with the verified result.
  No token streaming in Level 1.
- The browser calls a Next.js route handler (`/api/backend/*`) that streams request and
  response bodies to FastAPI, so there is no CORS and no buffering.

## Consequences

Identical behaviour on Windows, Linux and CI. Perceived latency is covered by visible stages;
token streaming can be added later for Anthropic only.
