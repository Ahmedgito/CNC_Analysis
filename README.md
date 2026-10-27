# CNC Part Analyzer

Ask questions about a CNC part in plain language. The app reads the part's Excel manufacturing
record, PDF engineering drawing and IGES 3D model, answers only from those files, cites the exact
cell, drawing callout or model feature behind every value, and flags where the files disagree.

How it works, how each file type is read, how the LLM is used and the limitations are in the
**[technical document](docs/TECHNICAL.md)**.

## Architecture

```mermaid
flowchart LR
  subgraph Browser
    UI[Next.js app<br/>record · drawing · 3D viewer · chat<br/>linked selection]
  end
  UI -- "/api/backend/* (same-origin, streamed)" --> Proxy[Next.js route handler]
  Proxy -- REST + SSE --> API[FastAPI]
  subgraph Backend
    API --> Guard[Question guard]
    Guard --> Ctx[Record context<br/>cells · drawing facts · model features<br/>three-way cross-checks]
    Ctx --> GW[Failover gateway]
    GW --> A[Anthropic<br/>claude-opus-5-5]
    GW -. fallback .-> G[Groq<br/>gpt-oss-120b]
    GW -. no keys .-> F[Offline rules]
    GW --> V[Verifier<br/>citations · numbers]
    V --> C[Compute engine<br/>safe AST · pint]
    API -. "only after a yes" .-> Vis[Vision model<br/>scanned drawings]
  end
  Ingest[Ingestion<br/>xlsx · xls · csv · pdf] --> X[Three-way cross-check<br/>units · conventions · odd one out]
  IGES[IGES · OpenCascade<br/>isolated worker process] --> X
  X --> DB[(PostgreSQL 18<br/>cells · drawing facts · model facts · parts · calls)]
  Ingest --> Store[(File store<br/>PDFs · page images · meshes · projections)]
  IGES --> Store
  API --> DB
```

| Folder | Contents |
|---|---|
| `backend/` | FastAPI service, ingestion (Excel, PDF, IGES), cross-check, LLM gateway, CLI (`cnc`), tests, golden-set evaluation |
| `frontend/` | Next.js 16 web app |
| `data/` | Sample workbooks, drawings and IGES models, ingested by the demo |
| `docs/` | [Technical document](docs/TECHNICAL.md), design records ([docs/adr](docs/adr)), evaluation reports |

## Prerequisites

| Tool | Version | Needed for |
|---|---|---|
| [Docker](https://docs.docker.com/get-docker/) with Compose | recent | the one-command setup, or only the database |
| Python | 3.11–3.13 | the backend, when not run in Docker |
| [uv](https://docs.astral.sh/uv/) | recent | Python dependencies and commands |
| Node.js | 22 | the frontend, when not run in Docker |
| pnpm | 12 (`corepack enable` installs the pinned version) | frontend dependencies |
| PostgreSQL | 18 | the database, if you don't use the Docker one |

On **Linux**, the 3D geometry kernel needs the GL runtime libraries:

```bash
sudo apt-get install -y libgl1 libglu1-mesa libxrender1 libxext6
```

Windows and macOS need nothing extra.

API keys are optional. Without them the app answers with a built-in offline rules engine, and
each answer says so. Add `ANTHROPIC_API_KEY` (primary) and `GROQ_API_KEY` (fallback) for real
model answers.

## Option 1: run everything with Docker

```bash
git clone https://github.com/Ahmedgito/CNC_Analysis.git
cd CNC_Analysis
cp backend/.env.example backend/.env    # then add API keys if you have them
docker compose up --build
```

Open http://localhost:3000. Compose starts PostgreSQL (host port 5434), the API (port 8000) and
the web app (port 3000), applies the database migrations, and ingests everything in `data/` on
startup.

Stop with `Ctrl+C`; `docker compose down -v` also deletes the database volume.

## Option 2: run the API and web app locally

### 1. Database

Either start the Docker one (Postgres on host port **5434**, with `cnc` and `cnc_test` databases
already created):

```bash
docker compose up -d db
```

or use your own PostgreSQL 18 and create the databases:

```sql
CREATE ROLE cnc LOGIN PASSWORD 'cnc';
CREATE DATABASE cnc OWNER cnc;
CREATE DATABASE cnc_test OWNER cnc;   -- only needed for the tests
```

### 2. Backend

```bash
cd backend
cp .env.example .env                    # edit DATABASE_URL if not using the Docker database
uv sync                                 # installs dependencies, including the OpenCascade kernel
uv run alembic upgrade head             # creates the tables
uv run cnc ingest ../data               # reads the sample workbooks, drawings and models
uv run cnc serve                        # API on http://127.0.0.1:8000 (OpenAPI docs at /docs)
```

`cnc ingest` is safe to run again: unchanged files are skipped. It also accepts a single file or
another folder, and you can upload files through `POST /api/v1/ingest`.

### 3. Frontend

In a second terminal:

```bash
cd frontend
pnpm install
pnpm dev                                # http://localhost:3000
```

The web app reaches the API through its own `/api/backend` route. Set `BACKEND_URL` if the API is
not on `http://127.0.0.1:8000`.

### Check that it works

1. Open http://localhost:3000. The status pill in the header should say **Live**.
2. Pick part **2283**, press **Compare**, and ask: *Do the spreadsheet, drawing and 3D model
   agree?*
3. The answer should name the job card as the odd one out on the outer diameter (Ø50 against Ø48
   on the drawing and the model), with sources from all three files. Clicking a source highlights
   it in the spreadsheet, on the drawing and on the 3D model.

With [just](https://github.com/casey/just) installed, the same steps are `just db-up install migrate
ingest`, then `just api` and `just web` in two terminals. `just --list` shows every recipe.

## Configuration

Settings are read from environment variables or `backend/.env`. Every value has a working
default except the API keys.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://cnc:cnc@localhost:5434/cnc` | PostgreSQL connection |
| `ANTHROPIC_API_KEY` | unset | Primary LLM (an Anthropic Console key, `sk-ant-api03-…`) |
| `ANTHROPIC_AUTH_TOKEN` | unset | OAuth bearer token instead of the API key |
| `GROQ_API_KEY` | unset | Fallback LLM |
| `LLM_PRIMARY_PROVIDER`, `LLM_FALLBACK_PROVIDER` | `anthropic`, `groq` | `anthropic`, `claude_code`, `groq`, `fake` (offline rules) or `none` |
| `ANTHROPIC_MODEL`, `GROQ_MODEL` | `claude-opus-5-5`, `openai/gpt-oss-120b` | Model per provider |
| `LLM_EFFORT` | `medium` | Claude effort level |
| `CLAUDE_CODE_OAUTH_TOKEN`, `CLAUDE_CODE_MODEL`, `CLAUDE_CODE_BIN` | unset, `claude-opus-5-5`, auto | Internal testing only: Claude through a locally installed Claude Code CLI (`claude setup-token`) |
| `DATA_DIR`, `AUTO_INGEST` | `../data`, `false` | Ingest a folder when the API starts (Docker sets `true`) |
| `GEOMETRY_TIMEOUT_S`, `GEOMETRY_MEMORY_MB`, `IGES_MAX_MB` | `30`, `1536`, `25` | Limits for the isolated 3D geometry worker |
| `BACKEND_URL` (frontend) | `http://127.0.0.1:8000` | Where the web app's proxy sends API calls |

Reading **scanned** drawings needs a vision-capable provider (`ANTHROPIC_API_KEY`, or the Claude
Code provider) and the user's agreement in the chat.

## Tests

```bash
cd backend
uv run ruff check . && uv run ruff format --check . && uv run pyright
uv run pytest -q                        # needs the cnc_test database

cd ../frontend
pnpm lint && pnpm format:check && pnpm typecheck && pnpm test && pnpm build
```

The backend tests use `postgresql+psycopg://cnc:cnc@localhost:5434/cnc_test`; set
`DATABASE_URL_TEST` to point them elsewhere. No API keys are needed: tests and CI use the offline
rules engine.

To evaluate answers against the golden question set:

```bash
cd backend
uv run cnc eval --provider fake --out ../docs/eval/offline-rules.md        # no keys needed
uv run cnc eval --provider anthropic --out ../docs/eval/anthropic.md       # needs ANTHROPIC_API_KEY
```

## Maintenance commands

Run from `backend/`:

| Command | Use |
|---|---|
| `uv run cnc ingest <file or folder>` | Ingest spreadsheets, drawings and IGES models |
| `uv run cnc rebuild` | Regroup stored data into part records after an upgrade |
| `uv run cnc reprocess [files…]` | Re-measure stored IGES models with the current extractor and rebuild their 3D views |
| `uv run cnc reset-drawing <pdf>` | Re-read a drawing, discarding a vision reading of a scan |
| `uv run alembic upgrade head` | Apply new database migrations |

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ImportError` mentioning `OCP` or `libGL.so.1` | Install the GL runtime libraries listed under Prerequisites (Linux only) |
| Status pill says the API is unreachable | Start the backend (`uv run cnc serve`) or set `BACKEND_URL` for the frontend |
| `connection refused` on port 5434 | Start the database (`docker compose up -d db`) or point `DATABASE_URL` at your own server |
| Backend tests are all skipped | The test database is unreachable: create `cnc_test` or set `DATABASE_URL_TEST` |
| Answers say "offline rules" | No API key is configured; add `ANTHROPIC_API_KEY` or `GROQ_API_KEY` to `backend/.env` and restart the API |
| An uploaded `.igs` file is rejected | It is not ASCII IGES, or it exceeds `IGES_MAX_MB`; the error message names the reason |
| Garbled `Ø` or `±` in Windows terminal output | Set `PYTHONUTF8=1` (the `just` recipes do this) |

## License

MIT
