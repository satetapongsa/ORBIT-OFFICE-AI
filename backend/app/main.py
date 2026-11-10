"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anyio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.db import dispose_engines
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.core.redis import close_redis
from app.core.storage import get_storage

logger = get_logger(__name__)

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    logger.info(
        "application_startup",
        environment=settings.environment.value,
        version=__version__,
        ai_chat_provider=settings.ai_chat_provider.value,
        ai_embedding_provider=settings.ai_embedding_provider.value,
    )
    if settings.storage_auto_create_bucket and not settings.is_production:
        # Bounded so an unreachable object store never blocks API startup;
        # readiness reports the storage problem instead.
        try:
            with anyio.fail_after(settings.health_check_timeout_seconds * 2):
                await anyio.to_thread.run_sync(get_storage().ensure_bucket, abandon_on_cancel=True)
        except Exception as exc:
            logger.warning("storage_bucket_init_failed", error_type=type(exc).__name__)
    yield
    await close_redis()
    await dispose_engines()
    logger.info("application_shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=f"{settings.app_name} API",
        version=__version__,
        description="AI-Powered Office Management Platform — internal REST API.",
        docs_url="/api/docs" if settings.docs_enabled else None,
        redoc_url="/api/redoc" if settings.docs_enabled else None,
        openapi_url="/api/openapi.json" if settings.docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = settings

    register_exception_handlers(app)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"],
            expose_headers=["X-Request-ID"],
        )
    # Added last so it is the outermost middleware and wraps everything above.
    app.add_middleware(RequestContextMiddleware)

    app.include_router(api_router, prefix=API_PREFIX)
    return app


app = create_app()
