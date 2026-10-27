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
| 13 | 2 | Golden set + eval runner, real-provider runs, prompt fixes | done | Claude (via Claude Code) 42/42, Groq 41/42, offline 37/42; three issues found and fixed (Unicode hyphen, double unit conversion, banner revision) |
| 14 | 3 | Frontend scaffold: Next 16, Tailwind 4, TanStack Query, Zod, API client | done | shadcn dropped: user asked for Tailwind utilities only, no plain CSS |
| 15 | 3 | Part picker page and record viewer with sheet tabs | done | |
| 16 | 3 | Chat panel: SSE client, answer card, source chips with cell highlight, provider footer | done | Verified live in Chrome: stages stream, chips highlight cells, panels scroll independently |
| 17 | 3 | Frontend tests: Vitest (SSE parser, chips) + Playwright smoke | doing | 12 Vitest tests pass. Playwright not added yet; live browser check done by hand |
| 18 | 4 | Adversarial golden rows, schema-drift workbook, failover demo | doing | Drift workbook, injection and failover covered by tests; live failover needs keys |
| 19 | 4 | CI workflow, pre-commit, ADRs, README with eval table, smoke script | done | Both Docker images build; containerised stack passes `scripts/smoke.py` and streams SSE through the proxy. CI workflow not yet run on GitHub (no remote) |
| 20 | 5 | Demo rehearsal, fixes, Level 2 seam check | todo | |
| 21 | 5 | Enterprise frontend redesign: animated, responsive, 21st.dev component set | done | Spec in `docs/FRONTEND_DESIGN.md`. Grid Beam and AI Chat Input retrieved from 21st.dev; the rest written in their style (free tier allows 2 retrievals a day). Verified in Chrome at desktop and phone widths, dark and light, with a live Groq answer |
| 22 | 5 | Fix double unit conversion in compute (`c1 / 25.4` plus `unit_out: in` gave 0.1938 in for Ø125) | todo | Found in the live UI. Reject or neutralise conversion constants when `unit_out` is set, and tell the model not to put factors in the expression |

## Level 2 (PDF drawings)

Plan: [PLAN_LEVEL2.md](PLAN_LEVEL2.md). Branch `level2-pdf-drawings`. Both datasets are used:
the synthetic set (2280–2284, two workbooks, four drawings) and batch 2 (3001–3004, the messy
workshop export, four drawings including a scan and a two-sheet revision package).

| WP | Task | Status | Notes |
|---|---|---|---|
| 0 | Messy workbook hardening | done | Identity keys (`P-3001`, `003003`, `3001` are one part), separator rows, vertical part cards, archive sheets and superseded revisions as history, sheet banner units, hours columns |
| 1 | Source-neutral `Fact` evidence model | done | `fact_id` replaces `cell_id`; old answers still load. ADR 0006 |
| 2 | PDF extraction | done | pdfplumber words, rotated text, ruled tables, page orientation; title block (compound labels, `SEE NOTE n`), notes, typed dimension callouts, revision table; scanned / protected / damaged / oversized / active-content guards |
| 3 | Storage, migration 0002, file store, API | done | Content-addressed PDF store, pages rendered to PNG on demand, `drawing_fact` table, `cnc rebuild`, `cnc reset-drawing` |
| 4 | Cross-check engine | done | Deterministic verdicts per field with unit resolution; never `disagree` on an ambiguous unit. ADR 0007 |
| 5 | Prompt, verifier, offline rules for drawings | done | `<drawing>` and `<cross_checks>` blocks, 13 system rules; file and sheet names no longer count as unsupported numbers |
| 6 | Consent-gated vision for scans | done | `needs_consent` + `read_scan` action; Anthropic, Claude Code and static readers; values labelled `vision`. ADR 0008. Verified live on 3001 with Claude |
| 7 | Frontend | done | Drawing tab with rendered page and clickable callout boxes, cross-check tab, PDF / vision / history chips, consent button, scanned badge, `reading_scan` stage; verified in Chrome, light and dark |
| 8 | Golden set, eval, docs | done | 22 Level 2 golden rows (64 total), `needs_consent` scored as a deferral, verdict assertions, "answer names its file" metric; README, ADRs 0006–0008 |

Every planted case in both answer keys is reproduced: 2280 and 2281 agree; 2282 agrees after
inch conversion and Ra/RMS convention; 2283 material and OD disagree; 3001 is a scan that needs
consent; 3002 Rev A is history; 3003 material comes from note 3 and the hole count disagrees
(part card 6, master list and drawing 4); 3004 agrees after conversion; 2284 has no drawing.

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
| 2026-10-27 | Excel-vs-PDF cross-check lands in Level 2, computed in code | User choice; a model comparing free text "corrects" values (ADR 0007) |
| 2026-10-27 | Scanned PDFs: tell the user, read with a vision model only after a yes | User choice (ADR 0008) |
| 2026-10-27 | Services run natively (PostgreSQL 18 on 5433), not in Docker, on the dev machine | User instruction; tests use `DATABASE_URL_TEST` |

## How to run (current state)

Native services on the dev machine (PostgreSQL 18 on port 5433, role and databases `cnc`,
`cnc_test`):

```
cd backend && uv sync
uv run alembic upgrade head
uv run cnc ingest ../data                    # idempotent; workbooks and drawings
PYTHONUTF8=1 uv run cnc serve --port 8000    # http://127.0.0.1:8000/docs
DATABASE_URL_TEST=postgresql+psycopg://cnc:cnc@localhost:5433/cnc_test uv run pytest -q   # 264 tests
uv run cnc eval --provider claude_code --out ../docs/eval/claude-code.md                 # 64/64
uv run cnc reset-drawing ../data/3001_gear_blank_scan.pdf   # forget a vision reading of the scan
cd ../frontend && pnpm install && pnpm dev   # http://localhost:3000; pnpm test (24)
```

## Next up

1. Push: `gh auth refresh -h github.com -s workflow`, then push `main` and the
   `level2-pdf-drawings` branch and open a PR.
2. Re-run the Groq eval on the 64-question set (`uv run cnc eval --provider groq`, ~10 min at the
   free-tier pace) and update the README table.
3. Level 3: IGES bounding box, hole count and diameters as facts; three-way cross-check.

## Open items / blockers

| Item | Owner | Notes |
|---|---|---|
| Local Postgres credentials | user | App reads `DATABASE_URL` from `backend/.env`; Docker Postgres used for tests when available |
| `ANTHROPIC_API_KEY`, `GROQ_API_KEY` | user | Needed only for real-provider eval runs; CI uses the fake adapter |
| IGES files for Level 3 | team | Generated by `tools/generate_iges.py` (build123d) from the answer keys into `docs/spec26_synthetic_data/iges/` and `docs/spec26_batch2_hard/iges/`. 2283 modelled at D48 (PDF), 2284 intentionally has none. IGES ingestion still to do |
