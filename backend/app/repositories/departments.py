"""Department queries."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import Department, User


async def list_departments(session: AsyncSession) -> Sequence[Department]:
    stmt = select(Department).where(Department.deleted_at.is_(None)).order_by(Department.code)
    return (await session.scalars(stmt)).all()


async def get_by_id(session: AsyncSession, department_id: uuid.UUID) -> Department | None:
    return await session.scalar(
        select(Department).where(Department.id == department_id, Department.deleted_at.is_(None))
    )


async def code_taken(session: AsyncSession, code: str, exclude_id: uuid.UUID | None = None) -> bool:
    stmt = select(Department.id).where(Department.code == code, Department.deleted_at.is_(None))
    if exclude_id:
        stmt = stmt.where(Department.id != exclude_id)
    return (await session.scalar(stmt.limit(1))) is not None


async def count_members(session: AsyncSession, department_id: uuid.UUID) -> int:
    stmt = select(func.count()).where(
        User.department_id == department_id, User.deleted_at.is_(None)
    )
    return int(await session.scalar(stmt) or 0)


async def member_counts(session: AsyncSession) -> dict[uuid.UUID, int]:
    stmt = (
        select(User.department_id, func.count())
        .where(User.department_id.is_not(None), User.deleted_at.is_(None))
        .group_by(User.department_id)
    )
    rows = (await session.execute(stmt)).all()
    return {dept_id: int(count) for dept_id, count in rows if dept_id is not None}
