"""Application settings, read from environment variables and ``backend/.env``."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["anthropic", "claude_code", "groq", "fake", "none"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["dev", "test", "prod"] = "dev"
    log_format: Literal["console", "json"] = "console"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://cnc:cnc@localhost:5434/cnc"
    data_dir: Path = Path(__file__).resolve().parent.parent.parent / "data"
    auto_ingest: bool = False  # ingest DATA_DIR on startup (used by docker compose)
    max_upload_mb: int = 25
    # Original drawing bytes and rendered page images (content-addressed, safe to delete).
    store_dir: Path = Path(__file__).resolve().parent.parent / "var" / "store"
    pdf_max_pages: int = 20
    # IGES geometry runs in an isolated worker process with these limits (PLAN_LEVEL3 4.1).
    geometry_timeout_s: float = 30.0
    geometry_memory_mb: int = 1536
    iges_max_mb: int = 25
    geometry_inline: bool = False  # run the kernel in-process (tests, trusted CLI use only)
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # LLM
    llm_primary_provider: ProviderName = "anthropic"
    llm_fallback_provider: ProviderName = "groq"
    anthropic_model: str = "claude-opus-5-5"
    groq_model: str = "openai/gpt-oss-120b"
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    llm_max_tokens: int = 4096
    llm_timeout_s: float = 45.0
    llm_history_turns: int = 6
    breaker_fail_max: int = 3
    breaker_reset_s: float = 60.0
    anthropic_api_key: SecretStr | None = None
    anthropic_auth_token: SecretStr | None = None  # OAuth bearer token, used if no API key
    # Internal testing only: Claude through the official Claude Code CLI on a personal subscription
    # (token from `claude setup-token`). Production uses ANTHROPIC_API_KEY.
    claude_code_oauth_token: SecretStr | None = None
    claude_code_bin: str | None = None  # auto-detected when unset
    claude_code_model: str = "claude-opus-5-5"
    claude_code_timeout_s: float = 180.0
    groq_api_key: SecretStr | None = None

    # USD per million tokens (input, output); used only for the cost column in llm_call.
    # Approximate list prices; override via MODEL_PRICES if the provider pages differ.
    model_prices: dict[str, tuple[float, float]] = Field(
        default_factory=lambda: {
            "claude-opus-5-5": (4.0, 20.0),
            "claude-sonnet-5-5": (2.0, 10.0),
            "claude-haiku-5-5": (0.10, 0.50),
            "openai/gpt-oss-120b": (0.15, 0.60),
        }
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def geometry_worker(settings: Settings):
    """The shared geometry worker for these settings (imported lazily; no kernel in the API)."""
    from app.geometry.worker import get_worker

    return get_worker(
        settings.geometry_timeout_s,
        settings.geometry_memory_mb,
        settings.iges_max_mb * 1024 * 1024,
        settings.geometry_inline,
    )
