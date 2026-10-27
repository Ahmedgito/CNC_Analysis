"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import ask, conversations, drawings, health, ingest, parts
from app.api.deps import ProblemError, problem_response
from app.config import Settings, get_settings
from app.db.session import make_engine, make_session_factory
from app.llm.gateway import FailoverGateway, build_gateway
from app.llm.vision import VisionProvider, build_vision
from app.logging_setup import configure_logging, log
from app.services.file_store import FileStore
from app.services.ingest_service import ingest_paths
from app.services.vision_service import VisionService

API_PREFIX = "/api/v1"


def create_app(
    settings: Settings | None = None,
    gateway: FailoverGateway | None = None,
    vision: VisionProvider | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(settings.database_url)
        app.state.settings = settings
        app.state.engine = engine
        app.state.session_factory = make_session_factory(engine)
        app.state.gateway = gateway or build_gateway(settings)
        app.state.store = FileStore(settings.store_dir)
        vision_provider = vision if vision is not None else build_vision(settings)
        app.state.vision = VisionService(
            app.state.session_factory, app.state.store, vision_provider, settings.model_prices
        )
        log.info(
            "startup.vision",
            provider=f"{vision_provider.name}:{vision_provider.model}" if vision_provider else None,
        )
        log.info(
            "startup.llm",
            providers=[f"{p.name}:{p.model}" for p in app.state.gateway.providers],
        )
        if settings.auto_ingest and settings.data_dir.exists():
            outcomes = await run_in_threadpool(
                ingest_paths,
                app.state.session_factory,
                settings.data_dir,
                app.state.store,
                settings.pdf_max_pages,
            )
            log.info("startup.auto_ingest", files=[(o.file_name, o.status) for o in outcomes])
        log.info("startup.ready", env=settings.app_env)
        yield
        engine.dispose()

    app = FastAPI(
        title="SPEC'26 CNC Part Analyzer",
        version="0.1.0",
        description=(
            "Evidence-grounded answers about CNC parts from their manufacturing records and "
            "PDF engineering drawings. Every answer cites the exact spreadsheet cell or drawing "
            "region it used, cross-checks the two sources, or says the information is not in "
            "the files."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(CorrelationIdMiddleware, header_name="X-Request-ID")

    @app.exception_handler(ProblemError)
    async def _problem(_: Request, exc: ProblemError) -> JSONResponse:
        return problem_response(exc.status, exc.title, exc.detail, **exc.extra)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()
        ]
        return problem_response(422, "Invalid request", "Request validation failed", errors=errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return problem_response(exc.status_code, "HTTP error", str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", error=str(exc))
        return problem_response(
            500, "Internal error", "Unexpected server error; see logs with the request id"
        )

    app.include_router(health.router)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(parts.router, prefix=API_PREFIX)
    app.include_router(ingest.router, prefix=API_PREFIX)
    app.include_router(ask.router, prefix=API_PREFIX)
    app.include_router(conversations.router, prefix=API_PREFIX)
    app.include_router(drawings.router, prefix=API_PREFIX)
    return app
