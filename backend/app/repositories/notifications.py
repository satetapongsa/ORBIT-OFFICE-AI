"""Notification queries. Every query is scoped to one recipient (``user_id``)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationPreference


async def list_for_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    page: int,
    page_size: int,
    unread_only: bool = False,
) -> tuple[Sequence[Notification], int]:
    stmt = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await session.scalars(
        stmt.order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return rows.all(), total


async def count_unread(session: AsyncSession, user_id: uuid.UUID) -> int:
    stmt = select(func.count(Notification.id)).where(
        Notification.user_id == user_id, Notification.read_at.is_(None)
    )
    return await session.scalar(stmt) or 0


async def get_for_user(
    session: AsyncSession, user_id: uuid.UUID, notification_id: uuid.UUID
) -> Notification | None:
    """The notification, only if it belongs to ``user_id`` (others are indistinguishable)."""
    stmt = select(Notification).where(
        Notification.id == notification_id, Notification.user_id == user_id
    )
    return await session.scalar(stmt)


async def mark_all_read(session: AsyncSession, user_id: uuid.UUID, now: datetime) -> int:
    result = await session.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=now)
        .returning(Notification.id)
    )
    return len(result.all())


async def email_preferences(session: AsyncSession, user_id: uuid.UUID) -> dict[str, bool]:
    rows = await session.execute(
        select(NotificationPreference.type, NotificationPreference.email_enabled).where(
            NotificationPreference.user_id == user_id
        )
    )
    return {r[0]: r[1] for r in rows}


async def upsert_email_preference(
    session: AsyncSession, user_id: uuid.UUID, kind: str, enabled: bool
) -> None:
    stmt = (
        pg_insert(NotificationPreference)
        .values(user_id=user_id, type=kind, email_enabled=enabled)
        .on_conflict_do_update(
            index_elements=["user_id", "type"],
            set_={"email_enabled": enabled, "updated_at": func.now()},
        )
    )
    await session.execute(stmt)
