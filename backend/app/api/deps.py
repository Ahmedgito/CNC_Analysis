"""Shared FastAPI dependencies and RFC 7807 error helpers."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Any

from asgi_correlation_id.context import correlation_id
from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import Settings
from app.services.file_store import FileStore


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_session(request: Request) -> Iterator[Session]:
    session: Session = request.app.state.session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_store(request: Request) -> FileStore:
    return request.app.state.store


SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
StoreDep = Annotated[FileStore, Depends(get_store)]


class ProblemError(Exception):
    """An error rendered as ``application/problem+json``."""

    def __init__(self, status: int, title: str, detail: str, **extra: Any) -> None:
        super().__init__(detail)
        self.status, self.title, self.detail, self.extra = status, title, detail, extra


def problem_response(status: int, title: str, detail: str, **extra: Any) -> JSONResponse:
    body = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "detail": detail,
        "request_id": correlation_id.get(),
        **extra,
    }
    return JSONResponse(body, status_code=status, media_type="application/problem+json")
