"""Chat and action queries. Every function filters by the owner — chats are private."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import AiActionRequest, ChatMessage, ChatRole, ChatSession


async def list_sessions(
    session: AsyncSession, user_id: uuid.UUID, *, page: int, page_size: int
) -> tuple[Sequence[ChatSession], int]:
    stmt = select(ChatSession).where(
        ChatSession.user_id == user_id, ChatSession.deleted_at.is_(None)
    )
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await session.scalars(
        stmt.order_by(ChatSession.last_message_at.desc(), ChatSession.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return rows.all(), int(total)


async def get_session(
    session: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID, *, for_update: bool = False
) -> ChatSession | None:
    stmt = select(ChatSession).where(
        ChatSession.id == session_id,
        ChatSession.user_id == user_id,
        ChatSession.deleted_at.is_(None),
    )
    if for_update:
        stmt = stmt.with_for_update()
    return await session.scalar(stmt)


async def list_messages(session: AsyncSession, session_id: uuid.UUID) -> Sequence[ChatMessage]:
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at, ChatMessage.id)
    )
    return (await session.scalars(stmt)).all()


async def recent_messages(
    session: AsyncSession, session_id: uuid.UUID, *, limit: int
) -> list[ChatMessage]:
    """The last ``limit`` messages, trimmed to start at a user/system turn so tool calls and
    their results are never split."""
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
    )
    rows = list(reversed((await session.scalars(stmt)).all()))
    starts = {ChatRole.USER.value, ChatRole.SYSTEM.value}
    while rows and rows[0].role not in starts:
        rows.pop(0)
    return rows


async def count_messages(session: AsyncSession, session_id: uuid.UUID) -> int:
    stmt = select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session_id)
    return int(await session.scalar(stmt) or 0)


async def list_actions(session: AsyncSession, session_id: uuid.UUID) -> Sequence[AiActionRequest]:
    stmt = (
        select(AiActionRequest)
        .where(AiActionRequest.session_id == session_id)
        .order_by(AiActionRequest.created_at, AiActionRequest.id)
    )
    return (await session.scalars(stmt)).all()


async def get_action(
    session: AsyncSession, user_id: uuid.UUID, action_id: uuid.UUID, *, for_update: bool = False
) -> AiActionRequest | None:
    stmt = (
        select(AiActionRequest)
        .join(ChatSession, ChatSession.id == AiActionRequest.session_id)
        .where(
            AiActionRequest.id == action_id,
            AiActionRequest.user_id == user_id,
            ChatSession.deleted_at.is_(None),
        )
    )
    if for_update:
        stmt = stmt.with_for_update(of=AiActionRequest)
    return await session.scalar(stmt)
