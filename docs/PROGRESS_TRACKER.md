# Progress Tracker: SPEC'26 CNC Part Analyzer

Read this file first when resuming work. Update the status and notes columns as tasks land.
Full design: [docs/PLAN.md](PLAN.md). Current target: **Level 1 (Core)**, Excel record only.

Status key: `todo` · `doing` · `done` · `blocked` · `cut`

## Level 1 build order

| # | Day | Task | Status | Evidence / notes |
|---|---|---|---|---|
| 1 | 1 | Repo skeleton: root `.gitignore`, `.env.example`, `docker-compose.yml`, `justfile`, `data/` sample workbooks | done | |
| 2 | 1 | Backend scaffold: uv project, `create_app()`, config, structlog, request IDs, `/healthz` `/readyz` | done | RFC 7807 errors, `X-Request-ID` on every response |
| 3 | 1 | Ingestion: readers (xlsx two-load, xls, csv), RawCell normalisation | done | Magic-byte sniffing; formulas keep cached values |
| 4 | 1 | Ingestion: header-row detection, banners, canonical header mapping, unit suffixes | done | 24 canonical fields; unit row joined into header |
| 5 | 1 | Ingestion: part-number column, text part keys, attributes vs rows sheets, part record JSON | done | Continuation rows forward-filled with warning |
| 6 | 1 | Ingestion tests against both sample workbooks plus drift fixtures (csv, merged header, hidden sheet, poisoned cell) | done | `tests/unit/test_ingestion.py`, `tests/fixtures/workbooks.py` |
| 7 | 1 | Persistence: SQLAlchemy models, Alembic 0001, repositories, sha256 idempotency | done | Changed file supersedes old run; old cells kept for audit |
| 8 | 1 | API: `GET /parts`, `GET /parts/{pn}` with suggestions, `POST /ingest`, `cnc ingest` CLI | done | |
| 9 | 2 | LLM: `AnswerDraft` schema, frozen system prompt, deterministic record renderer | done | Values JSON-encoded, `<` `>` escaped (test caught a tag-forging hole) |
| 10 | 2 | LLM: Fake, Anthropic, Groq adapters and `FailoverGateway` (retry, fallback, breaker) | done | Anthropic adapter also enables server-side refusal fallback (`fallbacks="default"`) |
| 11 | 2 | Verifier, compute engine (safe expressions, pint units), question guard | done | Verifier also auto-links uncited values and flags ungrounded numbers |
| 12 | 2 | `POST /parts/{pn}/ask` JSON + SSE, conversations, `llm_call` logging | done | One re-ask when every citation fails verification |
| 13 | 2 | Golden set + eval runner, real-provider runs, prompt fixes | blocked | 42-question set + `cnc eval` done; offline baseline 37/42 in `docs/eval/offline-rules.md`. Real runs need API keys |
| 14 | 3 | Frontend scaffold: Next 16, Tailwind 4, TanStack Query, Zod, API client | done | shadcn dropped: user asked for Tailwind utilities only, no plain CSS |
| 15 | 3 | Part picker page and record viewer with sheet tabs | done | |
| 16 | 3 | Chat panel: SSE client, answer card, source chips with cell highlight, provider footer | done | Verified live in Chrome: stages stream, chips highlight cells, panels scroll independently |
| 17 | 3 | Frontend tests: Vitest (SSE parser, chips) + Playwright smoke | doing | 12 Vitest tests pass. Playwright not added yet; live browser check done by hand |
| 18 | 4 | Adversarial golden rows, schema-drift workbook, failover demo | doing | Drift workbook, injection and failover covered by tests; live failover needs keys |
| 19 | 4 | CI workflow, pre-commit, ADRs, README with eval table, smoke script | done | Both Docker images build; containerised stack passes `scripts/smoke.py` and streams SSE through the proxy. CI workflow not yet run on GitHub (no remote) |
| 20 | 5 | Demo rehearsal, fixes, Level 2 seam check | todo | |
| 21 | 5 | Enterprise frontend redesign: animated, responsive, 21st.dev component set | done | Spec in `docs/FRONTEND_DESIGN.md`. Grid Beam and AI Chat Input retrieved from 21st.dev; the rest written in their style (free tier allows 2 retrievals a day). Verified in Chrome at desktop and phone widths, dark and light, with a live Groq answer |
| 22 | 5 | Fix double unit conversion in compute (`c1 / 25.4` plus `unit_out: in` gave 0.1938 in for Ø125) | todo | Found in the live UI. Reject or neutralise conversion constants when `unit_out` is set, and tell the model not to put factors in the expression |

## Acceptance checklist (Level 1)

- [x] Any part number in any ingested workbook resolves (2280–2284 from both workbooks)
- [x] Tolerant lookup: `2280`, `2280.0`, ` 2280 ` collide; suffixes offered as suggestions
- [x] Every claim has verified cell evidence; unverifiable claims are stripped
- [x] Out-of-record questions (price, customer, delivery, weight) answer "Not found in the provided files"
- [x] Arithmetic and unit conversion done in code with working shown
- [x] Nonexistent part, other-part comparison, injection, garbage input, PDF/IGES questions all tested
- [x] Anthropic to Groq failover works and is visible in answer metadata (scripted-provider tests; live run pending keys)
- [x] Re-ingest is idempotent; unknown headers ingest without code changes
- [x] Three-command quick start; CI checks green locally without API keys (GitHub run pending a remote)

## Decisions log

| Date | Decision | Why |
|---|---|---|
| 2026-10-27 | Level 1 first, Levels 2/3 later | User instruction: stabilise core before PDF/IGES |
| 2026-10-27 | Claude `claude-opus-5-5` primary, Groq `openai/gpt-oss-120b` fallback | User choice; Groq deprecated Llama on non-enterprise tiers in Aug 2026 |
| 2026-10-27 | Structured outputs + own evidence array + code verifier, not native citations | Anthropic citations cannot combine with structured outputs; Groq parity |
| 2026-10-27 | SSE stage events, no token streaming in Level 1 | Verifier must run before display; Groq cannot stream schema-constrained output |
| 2026-10-27 | psycopg3, text part keys, cells + JSONB record | See ADRs in `docs/adr/` |
| 2026-10-27 | Sync SQLAlchemy sessions in FastAPI's threadpool; async only for LLM I/O | psycopg async mode does not run on Windows' default event loop; one code path for Windows, Linux and CI |
| 2026-10-27 | Per-provider model settings (`ANTHROPIC_MODEL`, `GROQ_MODEL`) | Swapping primary/fallback order must not swap model names |
| 2026-10-27 | Offline rules provider (`offline-rules`) for CI, evals and keyless demos | Deterministic; reads only the prompt, so it exercises the real pipeline |
| 2026-10-27 | Tailwind utility classes only; no shadcn, no hand-written CSS | User instruction |
| 2026-10-27 | Browser talks to a Next route handler proxy, not FastAPI directly | No CORS; rewrites would buffer SSE |
| 2026-10-27 | `claude_code` provider: Claude via the official CLI on a personal subscription, internal testing only | Subscription tokens are refused by the raw API; pattern taken from EM-AI-FACTORY (ADR 0005). Production stays on `ANTHROPIC_API_KEY` |
| 2026-10-27 | Numbers in rows the answer cites are linked, not flagged | Real model run flagged "Op 20" as ungrounded; invented numbers elsewhere are still flagged |

## How to run (current state)

```
docker compose up -d db                      # Postgres 18 on host port 5434 (+ cnc_test database)
cd backend && uv sync
uv run alembic upgrade head
uv run cnc ingest ../data                    # idempotent
uv run cnc serve                             # http://127.0.0.1:8000/docs
uv run pytest -q                             # 141 tests, no API keys needed
uv run cnc eval --provider fake --out ../docs/eval/offline-rules.md
cd ../frontend && pnpm install && pnpm dev   # http://localhost:3000
uv run python scripts/smoke.py              # from backend/, against a running API
```

## Next up

1. Add `ANTHROPIC_API_KEY` and `GROQ_API_KEY` to `backend/.env`, run `just eval anthropic` and `just eval groq`, fix any prompt issues the per-question table shows, and put the numbers in the README table.
2. Live failover demo: start with an unreachable Anthropic endpoint and confirm the answer footer shows the Groq fallback.
3. Optional: Playwright smoke test of the UI (pick part, ask, chip highlights the cell).
4. Then Level 2: PDF title block and dimension extraction.

## Open items / blockers

| Item | Owner | Notes |
|---|---|---|
| Local Postgres credentials | user | App reads `DATABASE_URL` from `backend/.env`; Docker Postgres used for tests when available |
| `ANTHROPIC_API_KEY`, `GROQ_API_KEY` | user | Needed only for real-provider eval runs; CI uses the fake adapter |
| IGES files for Level 3 | team | Not in the synthetic set; model in FreeCAD from `ground_truth.json` |
