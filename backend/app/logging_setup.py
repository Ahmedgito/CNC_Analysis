"""structlog setup: console output in dev, JSON lines in prod, request id on every line."""

from __future__ import annotations

import logging
import sys

import structlog
from asgi_correlation_id.context import correlation_id


def _add_request_id(_logger: object, _method: str, event_dict: dict) -> dict:
    rid = correlation_id.get()
    if rid:
        event_dict.setdefault("request_id", rid)
    return event_dict


def configure_logging(level: str = "INFO", fmt: str = "console") -> None:
    shared = [
        structlog.contextvars.merge_contextvars,
        _add_request_id,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    renderer = (
        structlog.processors.JSONRenderer()
        if fmt == "json"
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )
    structlog.configure(
        processors=[*shared, structlog.processors.format_exc_info, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(
        level=level.upper(), stream=sys.stderr, format="%(levelname)s %(name)s %(message)s"
    )
    for noisy in ("httpx", "httpcore", "anthropic", "groq"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


log = structlog.get_logger("cnc")
