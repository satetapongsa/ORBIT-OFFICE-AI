"""Employee directory queries. Only ``users`` columns are read here — HR data lives in
``employee_hr_profiles`` and is loaded by :func:`get_hr_profile` alone."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import EmployeeHrProfile
from app.models.identity import Department, User


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def list_directory(
    session: AsyncSession,
    *,
    q: str | None,
    department_id: uuid.UUID | None,
    include_inactive: bool,
    page: int,
    page_size: int,
) -> tuple[Sequence[User], int]:
    stmt = select(User).where(User.deleted_at.is_(None))
    if not include_inactive:
        stmt = stmt.where(User.is_active.is_(True))
    if department_id is not None:
        stmt = stmt.where(User.department_id == department_id)
    if q and q.strip():
        pattern = f"%{_escape_like(q.strip())}%"
        stmt = stmt.where(
            or_(
                User.display_name.ilike(pattern, escape="\\"),
                User.first_name.ilike(pattern, escape="\\"),
                User.last_name.ilike(pattern, escape="\\"),
                User.job_title.ilike(pattern, escape="\\"),
                User.email.ilike(pattern, escape="\\"),
                User.employee_code.ilike(pattern, escape="\\"),
            )
        )
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await session.scalars(
        stmt.order_by(User.display_name, User.id).offset((page - 1) * page_size).limit(page_size)
    )
    return rows.unique().all(), int(total)


async def get_employee(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))


async def department_manager(
    session: AsyncSession, department_id: uuid.UUID | None
) -> tuple[uuid.UUID, str] | None:
    if department_id is None:
        return None
    stmt = (
        select(User.id, User.display_name)
        .join(Department, Department.manager_id == User.id)
        .where(
            Department.id == department_id,
            Department.deleted_at.is_(None),
            User.deleted_at.is_(None),
        )
    )
    row = (await session.execute(stmt)).first()
    return (row[0], row[1]) if row else None


async def get_hr_profile(session: AsyncSession, user_id: uuid.UUID) -> EmployeeHrProfile | None:
    return await session.get(EmployeeHrProfile, user_id, populate_existing=True)
