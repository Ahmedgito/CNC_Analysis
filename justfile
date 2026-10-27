# Task runner: https://github.com/casey/just  (Windows: `winget install Casey.Just`)
# Every recipe is also runnable by hand; see README "Run without just".

set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]
set dotenv-load := false

export PYTHONUTF8 := "1"

default:
    @just --list

# Start Postgres (host port 5434) in Docker
db-up:
    docker compose up -d db

# Install backend and frontend dependencies
install:
    cd backend; uv sync
    cd frontend; pnpm install

# Apply database migrations
migrate:
    cd backend; uv run alembic upgrade head

# Ingest every spreadsheet, drawing and IGES model under data/ (idempotent)
ingest:
    cd backend; uv run cnc ingest ../data

# Run the API on :8000 (offline rules engine unless API keys are set in backend/.env)
api:
    cd backend; uv run cnc serve --reload

# Re-measure stored IGES models with the current extractor (after an upgrade)
reprocess:
    cd backend; uv run cnc reprocess

# Run the web app on :3000
web:
    cd frontend; pnpm dev

# Everything the CI runs
ci: lint test

lint:
    cd backend; uv run ruff check .; uv run ruff format --check .; uv run pyright
    cd frontend; pnpm format:check; pnpm lint; pnpm typecheck

test:
    cd backend; uv run pytest -q
    cd frontend; pnpm test

# Golden-set evaluation: just eval anthropic | groq | fake
eval provider="fake":
    cd backend; uv run cnc eval --provider {{provider}} --out ../docs/eval/{{provider}}.md

# Full stack in containers (Postgres + API + web) on http://localhost:3000
up:
    docker compose up --build
