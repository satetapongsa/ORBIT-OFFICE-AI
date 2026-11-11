"""Role and permission queries."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import Permission, Role, UserRole


async def list_roles(session: AsyncSession) -> Sequence[Role]:
    return (await session.scalars(select(Role).order_by(Role.is_system.desc(), Role.code))).all()


async def get_by_id(session: AsyncSession, role_id: uuid.UUID) -> Role | None:
    return await session.get(Role, role_id)


async def get_by_code(session: AsyncSession, code: str) -> Role | None:
    return await session.scalar(select(Role).where(Role.code == code))


async def get_by_codes(session: AsyncSession, codes: Iterable[str]) -> list[Role]:
    wanted = set(codes)
    if not wanted:
        return []
    return list((await session.scalars(select(Role).where(Role.code.in_(wanted)))).all())


async def list_permissions(session: AsyncSession) -> Sequence[Permission]:
    return (await session.scalars(select(Permission).order_by(Permission.code))).all()


async def get_permissions_by_codes(session: AsyncSession, codes: Iterable[str]) -> list[Permission]:
    wanted = set(codes)
    if not wanted:
        return []
    return list(
        (await session.scalars(select(Permission).where(Permission.code.in_(wanted)))).all()
    )


async def count_users_with_role(session: AsyncSession, role_id: uuid.UUID) -> int:
    return int(await session.scalar(select(func.count()).where(UserRole.role_id == role_id)) or 0)
