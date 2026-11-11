"""Database engines and session factories.

psycopg 3 is used for both engines:
- async engine/session for FastAPI request handling;
- sync engine/session for Alembic migrations and Celery workers.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


@lru_cache
def get_async_engine() -> AsyncEngine:
    settings = get_settings()
    if settings.database_use_null_pool:
        return create_async_engine(
            settings.database_url.get_secret_value(),
            poolclass=NullPool,
            echo=settings.database_echo,
        )
    return create_async_engine(
        settings.database_url.get_secret_value(),
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,
        echo=settings.database_echo,
    )


@lru_cache
def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_async_engine(), expire_on_commit=False, autoflush=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request; rolled back if the handler raises."""
    async with get_async_session_factory()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@lru_cache
def get_sync_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.sync_database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_pre_ping=True,
        echo=settings.database_echo,
    )


@contextmanager
def sync_session_scope() -> Iterator[Session]:
    """Transactional scope for workers: commit on success, roll back on error."""
    factory = sessionmaker(get_sync_engine(), expire_on_commit=False, autoflush=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def dispose_engines() -> None:
    if get_async_engine.cache_info().currsize:
        await get_async_engine().dispose()
    if get_sync_engine.cache_info().currsize:
        get_sync_engine().dispose()
