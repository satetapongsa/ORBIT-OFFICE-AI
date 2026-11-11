"""Aggregates for analytics and reports.

Each query is restricted by a :class:`ScopeFilter` resolved from the caller's permissions in
``app.services.analytics`` (own work / own department / whole organisation). Counts and
lists never include soft-deleted rows.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.identity import User
from app.models.task import OPEN_TASK_STATUSES, Task, TaskAssignee
from app.models.ticket import OPEN_TICKET_STATUSES, Ticket
from app.repositories.task_access import assigned_to

ScopeKind = Literal["own", "department", "all"]


@dataclass(frozen=True, slots=True)
class ScopeFilter:
    kind: ScopeKind
    user_id: uuid.UUID
    department_id: uuid.UUID | None

    def tasks(self) -> ColumnElement[bool]:
        live = Task.deleted_at.is_(None)
        if self.kind == "own":
            return live & assigned_to(self.user_id)
        if self.kind == "department":
            return live & (Task.department_id == self.department_id)
        return live

    def tickets(self) -> ColumnElement[bool]:
        live = Ticket.deleted_at.is_(None)
        if self.kind == "own":
            return live & (Ticket.requester_id == self.user_id)
        if self.kind == "department":
            return live & Ticket.requester_id.in_(
                select(User.id).where(User.department_id == self.department_id)
            )
        return live

    def documents(self) -> ColumnElement[bool]:
        live = Document.deleted_at.is_(None)
        if self.kind == "own":
            return live & (Document.owner_id == self.user_id)
        if self.kind == "department":
            return live & (Document.department_id == self.department_id)
        return live


def _between(column: Any, start: datetime, end: datetime) -> ColumnElement[bool]:
    return and_(column >= start, column < end)


def _local_day(column: Any, tz: str) -> Any:
    return func.date(func.timezone(tz, column))


async def _counts(
    session: AsyncSession, column: Any, where: ColumnElement[bool]
) -> list[tuple[str, int]]:
    rows = await session.execute(
        select(column, func.count()).where(where).group_by(column).order_by(func.count().desc())
    )
    return [(str(r[0]), int(r[1])) for r in rows]


async def _daily(
    session: AsyncSession,
    column: Any,
    where: ColumnElement[bool],
    start: datetime,
    end: datetime,
    tz: str,
) -> dict[date, int]:
    day = _local_day(column, tz)
    rows = await session.execute(
        select(day, func.count()).where(where, _between(column, start, end)).group_by(day)
    )
    return {r[0]: int(r[1]) for r in rows}


# --- Tasks ------------------------------------------------------------------------------


async def task_metrics(
    session: AsyncSession, scope: ScopeFilter, start: datetime, end: datetime, now: datetime
) -> dict[str, Any]:
    where = scope.tasks()
    is_open = Task.status.in_(OPEN_TASK_STATUSES)
    row = (
        await session.execute(
            select(
                func.count().filter(is_open),
                func.count().filter(is_open, Task.due_at < now),
                func.count().filter(_between(Task.created_at, start, end)),
                func.count().filter(_between(Task.completed_at, start, end)),
                func.avg(
                    func.extract("epoch", Task.completed_at - Task.created_at) / 3600.0
                ).filter(_between(Task.completed_at, start, end)),
            ).where(where)
        )
    ).one()
    return {
        "open": int(row[0]),
        "overdue": int(row[1]),
        "created": int(row[2]),
        "completed": int(row[3]),
        "avg_completion_hours": float(row[4]) if row[4] is not None else None,
        "by_status": await _counts(session, Task.status, where),
        "open_by_priority": await _counts(session, Task.priority, where & is_open),
    }


async def task_daily(
    session: AsyncSession, scope: ScopeFilter, start: datetime, end: datetime, tz: str
) -> tuple[dict[date, int], dict[date, int]]:
    where = scope.tasks()
    created = await _daily(session, Task.created_at, where, start, end, tz)
    completed = await _daily(session, Task.completed_at, where, start, end, tz)
    return created, completed


async def workload(
    session: AsyncSession,
    scope: ScopeFilter,
    start: datetime,
    end: datetime,
    now: datetime,
    *,
    limit: int = 50,
) -> list[tuple[uuid.UUID, str, int, int, int]]:
    is_open = Task.status.in_(OPEN_TASK_STATUSES)
    open_count = func.count().filter(is_open)
    stmt = (
        select(
            User.id,
            User.display_name,
            open_count,
            func.count().filter(is_open, Task.due_at < now),
            func.count().filter(_between(Task.completed_at, start, end)),
        )
        .select_from(TaskAssignee)
        .join(Task, Task.id == TaskAssignee.task_id)
        .join(User, User.id == TaskAssignee.user_id)
        .where(scope.tasks())
        .group_by(User.id, User.display_name)
        .order_by(open_count.desc(), User.display_name)
        .limit(limit)
    )
    return [(r[0], r[1], int(r[2]), int(r[3]), int(r[4])) for r in await session.execute(stmt)]


async def task_rows(
    session: AsyncSession,
    scope: ScopeFilter,
    visible: ColumnElement[bool],
    start: datetime,
    end: datetime,
    *,
    limit: int,
) -> Sequence[Any]:
    """Tasks for exports: open ones plus those created or completed in the period.

    ``visible`` is the caller's task visibility predicate: a listed row is always one the
    caller could open (aggregates may cover more, e.g. a department's counts)."""
    assignees = (
        select(func.string_agg(User.display_name, ", "))
        .select_from(TaskAssignee)
        .join(User, User.id == TaskAssignee.user_id)
        .where(TaskAssignee.task_id == Task.id)
        .correlate(Task)
        .scalar_subquery()
    )
    stmt = (
        select(Task, assignees)
        .where(
            scope.tasks(),
            visible,
            Task.status.in_(OPEN_TASK_STATUSES)
            | _between(Task.created_at, start, end)
            | _between(Task.completed_at, start, end),
        )
        .order_by(Task.due_at.asc().nulls_last(), Task.created_at.desc())
        .limit(limit)
    )
    return (await session.execute(stmt)).all()


# --- Tickets ----------------------------------------------------------------------------


async def ticket_metrics(
    session: AsyncSession, scope: ScopeFilter, start: datetime, end: datetime
) -> dict[str, Any]:
    where = scope.tickets()
    row = (
        await session.execute(
            select(
                func.count().filter(Ticket.status.in_(OPEN_TICKET_STATUSES)),
                func.count().filter(_between(Ticket.created_at, start, end)),
                func.count().filter(_between(Ticket.resolved_at, start, end)),
                func.avg(
                    func.extract("epoch", Ticket.resolved_at - Ticket.created_at) / 3600.0
                ).filter(_between(Ticket.resolved_at, start, end)),
            ).where(where)
        )
    ).one()
    return {
        "open": int(row[0]),
        "opened": int(row[1]),
        "resolved": int(row[2]),
        "avg_resolution_hours": float(row[3]) if row[3] is not None else None,
        "by_status": await _counts(session, Ticket.status, where),
        "by_category": await _counts(
            session, Ticket.category, where & _between(Ticket.created_at, start, end)
        ),
    }


async def ticket_daily(
    session: AsyncSession, scope: ScopeFilter, start: datetime, end: datetime, tz: str
) -> tuple[dict[date, int], dict[date, int]]:
    where = scope.tickets()
    opened = await _daily(session, Ticket.created_at, where, start, end, tz)
    resolved = await _daily(session, Ticket.resolved_at, where, start, end, tz)
    return opened, resolved


async def ticket_rows(
    session: AsyncSession,
    scope: ScopeFilter,
    visible: ColumnElement[bool],
    start: datetime,
    end: datetime,
    *,
    limit: int,
) -> Sequence[Any]:
    requester = (
        select(User.display_name)
        .where(User.id == Ticket.requester_id)
        .correlate(Ticket)
        .scalar_subquery()
    )
    assignee = (
        select(User.display_name)
        .where(User.id == Ticket.assignee_id)
        .correlate(Ticket)
        .scalar_subquery()
    )
    stmt = (
        select(Ticket, requester, assignee)
        .where(
            scope.tickets(),
            visible,
            Ticket.status.in_(OPEN_TICKET_STATUSES) | _between(Ticket.created_at, start, end),
        )
        .order_by(Ticket.created_at.desc())
        .limit(limit)
    )
    return (await session.execute(stmt)).all()


# --- Documents --------------------------------------------------------------------------


async def document_metrics(
    session: AsyncSession, scope: ScopeFilter, start: datetime, end: datetime
) -> dict[str, Any]:
    where = scope.documents()
    row = (
        await session.execute(
            select(
                func.count(),
                func.count().filter(_between(Document.created_at, start, end)),
            ).where(where)
        )
    ).one()
    return {
        "total": int(row[0]),
        "uploaded": int(row[1]),
        "by_category": await _counts(session, Document.category, where),
    }
