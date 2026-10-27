from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
SAMPLE_A = DATA_DIR / "mfg_record_A.xlsx"
SAMPLE_B = DATA_DIR / "job_cards_B.xlsx"
TEST_DB_URL = os.environ.get(
    "DATABASE_URL_TEST", "postgresql+psycopg://cnc:cnc@localhost:5434/cnc_test"
)


@pytest.fixture(scope="session")
def sample_a() -> Path:
    return SAMPLE_A


@pytest.fixture(scope="session")
def sample_b() -> Path:
    return SAMPLE_B


# ----------------------------------------------------------------------------- database tests


def _db_available(url: str) -> bool:
    from sqlalchemy import create_engine, text

    try:
        engine = create_engine(url, connect_args={"connect_timeout": 2})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def db_url() -> str:
    if not _db_available(TEST_DB_URL):
        pytest.skip(
            f"test database not reachable at {TEST_DB_URL} (start it with: docker compose up -d db)"
        )
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    cfg.cmd_opts = type("Opts", (), {"x": [f"url={TEST_DB_URL}"]})()  # type: ignore[assignment]
    command.upgrade(cfg, "head")
    return TEST_DB_URL


def _truncate(db_url: str) -> None:
    from sqlalchemy import create_engine, text

    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE llm_call, message, conversation, part, part_fragment, cell, "
                "drawing_fact, ingest_run RESTART IDENTITY CASCADE"
            )
        )
    engine.dispose()


def make_test_settings(db_url: str, data_dir: Path, **overrides):
    from app.config import Settings

    values = {
        "app_env": "test",
        "database_url": db_url,
        "data_dir": data_dir,
        "store_dir": data_dir / ".store",
        "auto_ingest": False,
        "llm_primary_provider": "fake",
        "llm_fallback_provider": "none",
        "anthropic_api_key": None,
        "groq_api_key": None,
        **overrides,
    }
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def _ingest_samples(client) -> None:
    files = [
        ("files", (p.name, p.read_bytes(), "application/octet-stream"))
        for p in (SAMPLE_A, SAMPLE_B)
    ]
    resp = client.post("/api/v1/ingest", files=files)
    assert resp.status_code == 200, resp.text


@pytest.fixture
def settings(db_url: str, tmp_path: Path):
    _truncate(db_url)
    return make_test_settings(db_url, tmp_path)


@pytest.fixture
def client(settings) -> Iterator:
    """Fresh, empty database per test. Use for tests that write."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def ingested_client(client):
    """Fresh database with both sample workbooks ingested. Use for tests that write."""
    _ingest_samples(client)
    return client


@pytest.fixture(scope="module")
def seeded_client(db_url: str, tmp_path_factory) -> Iterator:
    """Samples ingested once per module. Read-only tests only."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    _truncate(db_url)
    settings = make_test_settings(db_url, tmp_path_factory.mktemp("data"))
    with TestClient(create_app(settings)) as c:
        _ingest_samples(c)
        yield c
