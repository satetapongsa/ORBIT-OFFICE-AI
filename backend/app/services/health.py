"""Dependency health checks used by the readiness endpoint."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import anyio
from sqlalchemy import text

from app import __version__
from app.core.config import Settings
from app.core.db import get_async_engine
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.core.storage import get_storage
from app.schemas.health import ComponentHealth, ComponentStatus, ReadinessResponse
from app.services.ai.config import AIComponentConfig, chat_config, embedding_config

logger = get_logger(__name__)

CheckFn = Callable[[], Awaitable[str | None]]


class DependencyCheckError(Exception):
    """Raised by a check with a short, safe-to-display reason."""


async def check_database() -> str | None:
    async with get_async_engine().connect() as conn:
        await conn.execute(text("SELECT 1"))
        has_vector = await conn.scalar(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        )
    if not has_vector:
        raise DependencyCheckError("pgvector extension missing — run `alembic upgrade head`")
    return "pgvector enabled"


async def check_redis() -> str | None:
    pong = await get_redis().ping()
    if not pong:
        raise DependencyCheckError("unexpected PING response")
    return None


async def check_storage() -> str | None:
    storage = get_storage()
    # abandon_on_cancel lets the readiness timeout fire even though boto3 is blocking.
    await anyio.to_thread.run_sync(storage.check_bucket, abandon_on_cancel=True)
    return f"bucket '{storage.bucket}' reachable"


async def _run_check(name: str, fn: CheckFn, timeout_seconds: float) -> ComponentHealth:
    start = time.perf_counter()
    try:
        async with asyncio.timeout(timeout_seconds):
            detail = await fn()
        status = ComponentStatus.OK
    except DependencyCheckError as exc:
        status, detail = ComponentStatus.ERROR, str(exc)
    except TimeoutError:
        status, detail = ComponentStatus.ERROR, "timed out"
    except Exception as exc:
        # Details go to the log only; the response stays generic.
        logger.warning("health_check_failed", component=name, error_type=type(exc).__name__)
        status, detail = ComponentStatus.ERROR, "unavailable"
    latency = round((time.perf_counter() - start) * 1000, 2)
    return ComponentHealth(
        name=name, status=status, required=True, latency_ms=latency, detail=detail
    )


def _ai_component(cfg: AIComponentConfig) -> ComponentHealth:
    if not cfg.enabled:
        return ComponentHealth(name=cfg.name, status=ComponentStatus.NOT_CONFIGURED, required=False)
    if cfg.problems:
        return ComponentHealth(
            name=cfg.name,
            status=ComponentStatus.ERROR,
            required=False,
            detail="; ".join(cfg.problems),
        )
    return ComponentHealth(
        name=cfg.name,
        status=ComponentStatus.CONFIGURED,
        required=False,
        detail=f"{cfg.provider.value}: {cfg.model} (connectivity not checked)",
    )


DEFAULT_CHECKS: dict[str, CheckFn] = {
    "database": check_database,
    "redis": check_redis,
    "object_storage": check_storage,
}


async def readiness(
    settings: Settings, checks: dict[str, CheckFn] | None = None
) -> ReadinessResponse:
    selected = checks if checks is not None else DEFAULT_CHECKS
    results = await asyncio.gather(
        *(
            _run_check(name, fn, settings.health_check_timeout_seconds)
            for name, fn in selected.items()
        )
    )
    components = [
        *results,
        _ai_component(chat_config(settings)),
        _ai_component(embedding_config(settings)),
    ]
    overall = (
        ComponentStatus.OK
        if all(c.status is ComponentStatus.OK for c in components if c.required)
        else ComponentStatus.ERROR
    )
    return ReadinessResponse(
        status=overall,
        service=settings.app_name,
        version=__version__,
        environment=settings.environment.value,
        checked_at=datetime.now(UTC),
        components=components,
    )
