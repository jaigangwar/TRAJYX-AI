"""TRAJYX API application factory.

Run locally:
    .venv/Scripts/python -m uvicorn app.main:app --reload --app-dir backend

Or via the helper script, which sets PYTHONPATH for the shared package:
    python scripts/dev_backend.py
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.repositories.factory import create_document_store, create_storage_backend
from app.services.auth.factory import create_auth_provider
from app.workers.analysis import AnalysisRunner, InProcessJobQueue

log = structlog.get_logger(__name__)

DESCRIPTION = """
TRAJYX converts CCTV-derived road behaviour into actionable safety intelligence.

The pipeline is: observe -> track -> understand -> predict -> warn -> learn.

**Data honesty contract.** Every record carries an `origin` of `MEASURED`,
`ESTIMATED` or `DEMO`, and every visual check can return
`UNABLE_TO_DETERMINE`. Values the system cannot support are never presented as
ground truth.
""".strip()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Validate configuration, build shared singletons, log resolved capabilities."""
    settings: Settings = app.state.settings

    errors = settings.startup_errors()
    if errors:
        for message in errors:
            log.error("startup.invalid_configuration", detail=message)
        raise RuntimeError("Invalid configuration: " + "; ".join(errors))

    # Built once per process: a Firestore client and a Firebase Admin app are
    # expensive to create and are designed to be long-lived.
    app.state.store = create_document_store(settings)
    app.state.storage = create_storage_backend(settings)
    app.state.auth_provider = create_auth_provider(settings, app.state.store)

    runner = AnalysisRunner(app.state.store, app.state.storage, settings)
    runner.bind_loop()
    app.state.job_queue = InProcessJobQueue(runner, concurrency=settings.worker_concurrency)

    log.info(
        "startup.ready",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
        data_backend=settings.resolved_data_backend.value,
        auth_backend=settings.resolved_auth_backend.value,
        storage_backend=settings.resolved_storage_backend.value,
        demo_mode=settings.demo_mode,
    )
    for note in settings.startup_warnings():
        log.warning("startup.note", detail=note)

    yield

    store = getattr(app.state, "store", None)
    if store is not None:
        await store.close()
    log.info("shutdown.complete")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI application. Accepts injected settings for tests."""
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=DESCRIPTION,
        default_response_class=ORJSONResponse,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )
    app.state.settings = settings

    # Order matters: request context is outermost so every later layer logs with it.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-Response-Time-ms"],
    )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "version": settings.app_version,
            "api": settings.api_prefix,
            "docs": "/docs" if not settings.is_production else "disabled",
        }

    return app


app = create_app()
