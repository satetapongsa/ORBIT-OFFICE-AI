"""Read-only aggregate queries behind the dashboard.

Callers decide *whether* a user may see an aggregate (see ``app.services.dashboard``);
these functions only compute it.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import ColumnElement, Date, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.principal import CurrentUser
from app.models.audit import AuditLog
from app.models.auth import UserSession
from app.models.document import Document, DocumentVersion
from app.models.identity import Department, User
from app.repositories.document_access import accessible_documents_condition


def _local_day(tz: str) -> ColumnElement[date]:
    """``occurred_at`` converted to a calendar date in the business time zone."""
    return cast(func.timezone(tz, AuditLog.occurred_at), Date)


async def count_active_sessions(session: AsyncSession, user_id: uuid.UUID, now: datetime) -> int:
    """Logins (refresh-token families) that can still be refreshed."""
    stmt = select(func.count(func.distinct(UserSession.family_id))).where(
        UserSession.user_id == user_id,
        UserSession.revoked_at.is_(None),
        UserSession.rotated_at.is_(None),
        UserSession.expires_at > now,
        UserSession.family_expires_at > now,
    )
    return await session.scalar(stmt) or 0


async def previous_login_at(session: AsyncSession, user_id: uuid.UUID) -> datetime | None:
    stmt = (
        select(AuditLog.occurred_at)
        .where(AuditLog.actor_id == user_id, AuditLog.action == "auth.login")
        .order_by(AuditLog.occurred_at.desc())
        .offset(1)
        .limit(1)
    )
    return await session.scalar(stmt)


async def daily_action_counts(
    session: AsyncSession,
    *,
    actions: Sequence[str],
    since: datetime,
    tz: str,
    actor_id: uuid.UUID | None = None,
) -> dict[tuple[date, str], int]:
    """Number of audit events per (local day, action) since ``since``."""
    day = _local_day(tz)
    stmt = (
        select(day.label("day"), AuditLog.action, func.count(AuditLog.id))
        .where(AuditLog.occurred_at >= since, AuditLog.action.in_(actions))
        .group_by("day", AuditLog.action)
    )
    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    rows = await session.execute(stmt)
    return {(row[0], row[1]): int(row[2]) for row in rows}


async def recent_activity(
    session: AsyncSession, *, limit: int, about_user: uuid.UUID | None = None
) -> list[tuple[AuditLog, uuid.UUID | None, str | None]]:
    """Latest audit events with the actor's display name.

    ``about_user`` limits the result to events the user performed or that targeted their account.
    """
    actor = aliased(User)
    stmt = select(AuditLog, actor.id, actor.display_name).outerjoin(
        actor, actor.id == AuditLog.actor_id
    )
    if about_user is not None:
        stmt = stmt.where(
            or_(
                AuditLog.actor_id == about_user,
                and_(AuditLog.entity_type == "user", AuditLog.entity_id == about_user),
            )
        )
    stmt = stmt.order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc()).limit(limit)
    rows = await session.execute(stmt)
    return [(row[0], row[1], row[2]) for row in rows]


async def user_counts(session: AsyncSession) -> tuple[int, int]:
    """(active, inactive) among users that are not soft-deleted."""
    stmt = select(
        func.count(User.id).filter(User.is_active.is_(True)),
        func.count(User.id).filter(User.is_active.is_(False)),
    ).where(User.deleted_at.is_(None))
    row = (await session.execute(stmt)).one()
    return int(row[0]), int(row[1])


async def count_departments(session: AsyncSession) -> int:
    stmt = select(func.count(Department.id)).where(Department.deleted_at.is_(None))
    return await session.scalar(stmt) or 0


async def headcount_by_department(
    session: AsyncSession,
) -> list[tuple[Department | None, int]]:
    """Active users per live department (largest first); ``None`` = no department."""
    # Users in a soft-deleted department count as "no department".
    stmt = (
        select(Department.id, func.count(User.id))
        .select_from(User)
        .outerjoin(
            Department,
            and_(Department.id == User.department_id, Department.deleted_at.is_(None)),
        )
        .where(User.deleted_at.is_(None), User.is_active.is_(True))
        .group_by(Department.id)
    )
    counts = [(row[0], int(row[1])) for row in await session.execute(stmt)]
    ids = [dept_id for dept_id, _ in counts if dept_id is not None]
    departments = (
        {d.id: d for d in await session.scalars(select(Department).where(Department.id.in_(ids)))}
        if ids
        else {}
    )
    result = [(departments.get(dept_id) if dept_id else None, n) for dept_id, n in counts]
    result.sort(key=lambda item: (-item[1], item[0].name if item[0] else "￿"))
    return result


async def count_accessible_documents(session: AsyncSession, user: CurrentUser) -> int:
    """Uses the single document access predicate — never re-implement ACL rules here."""
    stmt = select(func.count(Document.id)).where(accessible_documents_condition(user))
    return await session.scalar(stmt) or 0


async def my_document_counts(session: AsyncSession, user_id: uuid.UUID) -> tuple[int, int, int]:
    """(owned, current file pending/processing, current file failed) for live documents."""
    status = DocumentVersion.processing_status
    stmt = (
        select(
            func.count(Document.id),
            func.count(Document.id).filter(status.in_(["PENDING", "PROCESSING"])),
            func.count(Document.id).filter(status == "FAILED"),
        )
        .select_from(Document)
        .outerjoin(DocumentVersion, DocumentVersion.id == Document.current_version_id)
        .where(Document.owner_id == user_id, Document.deleted_at.is_(None))
    )
    row = (await session.execute(stmt)).one()
    return int(row[0]), int(row[1]), int(row[2])


async def recent_documents(
    session: AsyncSession, user: CurrentUser, *, limit: int
) -> list[tuple[Document, DocumentVersion | None]]:
    stmt = (
        select(Document, DocumentVersion)
        .outerjoin(DocumentVersion, DocumentVersion.id == Document.current_version_id)
        .where(accessible_documents_condition(user))
        .order_by(Document.updated_at.desc(), Document.id.desc())
        .limit(limit)
    )
    return [(r[0], r[1]) for r in await session.execute(stmt)]
