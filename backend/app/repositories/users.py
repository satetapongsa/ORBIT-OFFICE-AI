"""User queries."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import Permission, Role, User, UserRole, role_permissions


def _live() -> Select[User]:
    return select(User).where(User.deleted_at.is_(None))


async def get_by_id(
    session: AsyncSession, user_id: uuid.UUID, *, reload: bool = False
) -> User | None:
    """``reload=True`` refreshes an already-loaded instance (and its eager relations)."""
    stmt = _live().where(User.id == user_id)
    if reload:
        stmt = stmt.execution_options(populate_existing=True)
    return await session.scalar(stmt)


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    return await session.scalar(_live().where(func.lower(User.email) == email.strip().lower()))


async def email_taken(
    session: AsyncSession, email: str, exclude_id: uuid.UUID | None = None
) -> bool:
    stmt = select(User.id).where(func.lower(User.email) == email.strip().lower())
    if exclude_id:
        stmt = stmt.where(User.id != exclude_id)
    return (await session.scalar(stmt.limit(1))) is not None


async def employee_code_taken(
    session: AsyncSession, code: str, exclude_id: uuid.UUID | None = None
) -> bool:
    stmt = select(User.id).where(User.employee_code == code)
    if exclude_id:
        stmt = stmt.where(User.id != exclude_id)
    return (await session.scalar(stmt.limit(1))) is not None


async def permissions_for_user(session: AsyncSession, user_id: uuid.UUID) -> set[str]:
    stmt = (
        select(Permission.code)
        .join(role_permissions, role_permissions.c.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == role_permissions.c.role_id)
        .where(UserRole.user_id == user_id)
        .distinct()
    )
    return set((await session.scalars(stmt)).all())


async def list_users(
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
    q: str | None = None,
    department_id: uuid.UUID | None = None,
    is_active: bool | None = None,
    role_code: str | None = None,
) -> tuple[Sequence[User], int]:
    stmt = _live()
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                User.display_name.ilike(pattern),
                User.email.ilike(pattern),
                User.employee_code.ilike(pattern),
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
            )
        )
    if department_id:
        stmt = stmt.where(User.department_id == department_id)
    if is_active is not None:
        stmt = stmt.where(User.is_active.is_(is_active))
    if role_code:
        stmt = stmt.where(
            User.id.in_(
                select(UserRole.user_id)
                .join(Role, Role.id == UserRole.role_id)
                .where(Role.code == role_code)
            )
        )
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await session.scalars(
        stmt.order_by(User.display_name, User.id).offset((page - 1) * page_size).limit(page_size)
    )
    return rows.unique().all(), total


async def count_active_holders_of_role(session: AsyncSession, role_id: uuid.UUID) -> int:
    stmt = (
        select(func.count(func.distinct(User.id)))
        .join(UserRole, UserRole.user_id == User.id)
        .where(UserRole.role_id == role_id, User.is_active.is_(True), User.deleted_at.is_(None))
    )
    return int(await session.scalar(stmt) or 0)
