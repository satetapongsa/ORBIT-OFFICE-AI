"""Login session (refresh token) queries."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import PasswordResetToken, UserSession


async def get_by_token_hash_for_update(
    session: AsyncSession, token_hash: str
) -> UserSession | None:
    stmt = select(UserSession).where(UserSession.refresh_token_hash == token_hash).with_for_update()
    return await session.scalar(stmt)


async def family_is_active(session: AsyncSession, family_id: uuid.UUID, now: datetime) -> bool:
    stmt = select(
        exists().where(
            UserSession.family_id == family_id,
            UserSession.revoked_at.is_(None),
            UserSession.family_expires_at > now,
        )
    )
    return bool(await session.scalar(stmt))


async def revoke_family(
    session: AsyncSession, family_id: uuid.UUID, now: datetime, reason: str
) -> None:
    await session.execute(
        update(UserSession)
        .where(UserSession.family_id == family_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now, revoked_reason=reason)
    )


async def revoke_all_for_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    now: datetime,
    reason: str,
    *,
    except_family: uuid.UUID | None = None,
) -> None:
    stmt = (
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now, revoked_reason=reason)
    )
    if except_family is not None:
        stmt = stmt.where(UserSession.family_id != except_family)
    await session.execute(stmt)


async def get_reset_token_for_update(
    session: AsyncSession, token_hash: str
) -> PasswordResetToken | None:
    stmt = (
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == token_hash)
        .with_for_update()
    )
    return await session.scalar(stmt)


async def invalidate_reset_tokens(session: AsyncSession, user_id: uuid.UUID, now: datetime) -> None:
    await session.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user_id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
