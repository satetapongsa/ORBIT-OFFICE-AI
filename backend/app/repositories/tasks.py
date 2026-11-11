"""Task queries.

Every query that returns tasks filters with :func:`visible_tasks_condition` — never
re-implement visibility rules here. Helpers that take a ``task_id`` expect the caller to
have authorised it already.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.principal import CurrentUser
from app.models.identity import Department, User
from app.models.task import (
    OPEN_TASK_STATUSES,
    Task,
    TaskAssignee,
    TaskAttachment,
    TaskComment,
    TaskEvent,
    TaskPriority,
)
from app.repositories.task_access import assigned_to, visible_tasks_condition
from app.schemas.tasks import TaskScope, TaskSort


@dataclass(frozen=True, slots=True)
class TaskFilters:
    scope: TaskScope = "all"
    q: str | None = None
    status: str | None = None
    open_only: bool = False
    priority: str | None = None
    assignee_id: uuid.UUID | None = None
    overdue: bool = False


@dataclass(slots=True)
class TaskRow:
    task: Task
    creator_name: str
    department: Department | None
    comment_count: int
    attachment_count: int
    assignees: list[tuple[uuid.UUID, str]] = field(default_factory=list)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _counts() -> tuple[Any, Any]:
    comments = (
        select(func.count(TaskComment.id))
        .where(TaskComment.task_id == Task.id)
        .correlate(Task)
        .scalar_subquery()
    )
    attachments = (
        select(func.count(TaskAttachment.id))
        .where(TaskAttachment.task_id == Task.id)
        .correlate(Task)
        .scalar_subquery()
    )
    return comments, attachments


def _base(user: CurrentUser) -> Any:
    creator = aliased(User)
    comments, attachments = _counts()
    return (
        select(Task, creator.display_name, Department, comments, attachments)
        .join(creator, creator.id == Task.created_by)
        .outerjoin(Department, Department.id == Task.department_id)
        .where(visible_tasks_condition(user))
    )


def _row(row: Sequence[object]) -> TaskRow:
    task, creator_name, department, comment_count, attachment_count = row
    assert isinstance(task, Task)  # noqa: S101 - narrowing for mypy
    return TaskRow(
        task=task,
        creator_name=str(creator_name),
        department=department if isinstance(department, Department) else None,
        comment_count=int(str(comment_count or 0)),
        attachment_count=int(str(attachment_count or 0)),
    )


async def _attach_assignees(session: AsyncSession, rows: list[TaskRow]) -> list[TaskRow]:
    if not rows:
        return rows
    by_task = {r.task.id: r for r in rows}
    stmt = (
        select(TaskAssignee.task_id, User.id, User.display_name)
        .join(User, User.id == TaskAssignee.user_id)
        .where(TaskAssignee.task_id.in_(by_task))
        .order_by(TaskAssignee.created_at, User.display_name)
    )
    for task_id, uid, name in await session.execute(stmt):
        by_task[task_id].assignees.append((uid, name))
    return rows


_PRIORITY_RANK = case(
    {p.value: p.rank for p in TaskPriority},
    value=Task.priority,
)


async def list_tasks(
    session: AsyncSession,
    user: CurrentUser,
    filters: TaskFilters,
    *,
    now: datetime,
    sort: TaskSort,
    page: int,
    page_size: int,
) -> tuple[list[TaskRow], int]:
    stmt = _base(user)
    if filters.scope == "assigned":
        stmt = stmt.where(assigned_to(user.id))
    elif filters.scope == "created":
        stmt = stmt.where(Task.created_by == user.id)
    elif filters.scope == "department":
        if user.department_id is None:
            return [], 0
        stmt = stmt.where(Task.department_id == user.department_id)
    if filters.q:
        pattern = f"%{_escape_like(filters.q.strip())}%"
        stmt = stmt.where(
            or_(
                Task.title.ilike(pattern, escape="\\"),
                Task.description.ilike(pattern, escape="\\"),
            )
        )
    if filters.status:
        stmt = stmt.where(Task.status == filters.status)
    if filters.open_only:
        stmt = stmt.where(Task.status.in_(OPEN_TASK_STATUSES))
    if filters.priority:
        stmt = stmt.where(Task.priority == filters.priority)
    if filters.assignee_id:
        stmt = stmt.where(assigned_to(filters.assignee_id))
    if filters.overdue:
        stmt = stmt.where(Task.due_at < now, Task.status.in_(OPEN_TASK_STATUSES))

    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order: tuple[Any, ...] = {
        "due": (Task.due_at.asc().nulls_last(), _PRIORITY_RANK.desc(), Task.id),
        "updated": (Task.updated_at.desc(), Task.id.desc()),
        "created": (Task.created_at.desc(), Task.id.desc()),
        "priority": (_PRIORITY_RANK.desc(), Task.due_at.asc().nulls_last(), Task.id),
    }[sort]
    rows = [
        _row(r)
        for r in await session.execute(
            stmt.order_by(*order).offset((page - 1) * page_size).limit(page_size)
        )
    ]
    return await _attach_assignees(session, rows), int(total)


async def get_task(session: AsyncSession, user: CurrentUser, task_id: uuid.UUID) -> TaskRow | None:
    row = (await session.execute(_base(user).where(Task.id == task_id))).first()
    if row is None:
        return None
    return (await _attach_assignees(session, [_row(row)]))[0]


async def get_task_for_update(session: AsyncSession, task_id: uuid.UUID) -> Task | None:
    """Lock a live task row; call only after a visibility check."""
    stmt = select(Task).where(Task.id == task_id, Task.deleted_at.is_(None)).with_for_update()
    return await session.scalar(stmt)


async def assignee_ids(session: AsyncSession, task_id: uuid.UUID) -> list[uuid.UUID]:
    stmt = select(TaskAssignee.user_id).where(TaskAssignee.task_id == task_id)
    return list((await session.scalars(stmt)).all())


async def assignee_links(session: AsyncSession, task_id: uuid.UUID) -> Sequence[TaskAssignee]:
    stmt = select(TaskAssignee).where(TaskAssignee.task_id == task_id)
    return (await session.scalars(stmt)).all()


async def active_users(session: AsyncSession, ids: Sequence[uuid.UUID]) -> Sequence[User]:
    if not ids:
        return []
    stmt = select(User).where(User.id.in_(ids), User.deleted_at.is_(None), User.is_active.is_(True))
    return (await session.scalars(stmt)).all()


async def assignable_users(
    session: AsyncSession, department_id: uuid.UUID | None, q: str | None, *, limit: int
) -> Sequence[User]:
    """Active users; restricted to one department unless ``department_id`` is ``None``."""
    stmt = select(User).where(User.deleted_at.is_(None), User.is_active.is_(True))
    if department_id is not None:
        stmt = stmt.where(User.department_id == department_id)
    if q and q.strip():
        pattern = f"%{_escape_like(q.strip())}%"
        stmt = stmt.where(
            or_(
                User.display_name.ilike(pattern, escape="\\"),
                User.job_title.ilike(pattern, escape="\\"),
            )
        )
    return (await session.scalars(stmt.order_by(User.display_name).limit(limit))).all()


async def list_comments(
    session: AsyncSession, task_id: uuid.UUID
) -> list[tuple[TaskComment, str | None]]:
    stmt = (
        select(TaskComment, User.display_name)
        .outerjoin(User, User.id == TaskComment.author_id)
        .where(TaskComment.task_id == task_id)
        .order_by(TaskComment.created_at, TaskComment.id)
    )
    return [(r[0], r[1]) for r in await session.execute(stmt)]


async def get_comment(
    session: AsyncSession, task_id: uuid.UUID, comment_id: uuid.UUID
) -> TaskComment | None:
    stmt = select(TaskComment).where(TaskComment.id == comment_id, TaskComment.task_id == task_id)
    return await session.scalar(stmt)


async def list_attachments(
    session: AsyncSession, task_id: uuid.UUID
) -> list[tuple[TaskAttachment, str | None]]:
    stmt = (
        select(TaskAttachment, User.display_name)
        .outerjoin(User, User.id == TaskAttachment.uploaded_by)
        .where(TaskAttachment.task_id == task_id)
        .order_by(TaskAttachment.created_at.desc(), TaskAttachment.id)
    )
    return [(r[0], r[1]) for r in await session.execute(stmt)]


async def count_attachments(session: AsyncSession, task_id: uuid.UUID) -> int:
    stmt = select(func.count(TaskAttachment.id)).where(TaskAttachment.task_id == task_id)
    return int(await session.scalar(stmt) or 0)


async def get_attachment(
    session: AsyncSession, task_id: uuid.UUID, attachment_id: uuid.UUID
) -> TaskAttachment | None:
    stmt = select(TaskAttachment).where(
        TaskAttachment.id == attachment_id, TaskAttachment.task_id == task_id
    )
    return await session.scalar(stmt)


async def list_events(
    session: AsyncSession, task_id: uuid.UUID, *, limit: int
) -> list[tuple[TaskEvent, str | None]]:
    stmt = (
        select(TaskEvent, User.display_name)
        .outerjoin(User, User.id == TaskEvent.actor_id)
        .where(TaskEvent.task_id == task_id)
        .order_by(TaskEvent.created_at.desc(), TaskEvent.id.desc())
        .limit(limit)
    )
    return [(r[0], r[1]) for r in await session.execute(stmt)]


async def my_task_counts(
    session: AsyncSession, user: CurrentUser, now: datetime, soon: datetime
) -> tuple[int, int, int]:
    """(open tasks assigned to me, of which overdue, of which due before ``soon``)."""
    open_mine = (
        select(Task.id, Task.due_at)
        .where(
            visible_tasks_condition(user),
            assigned_to(user.id),
            Task.status.in_(OPEN_TASK_STATUSES),
        )
        .subquery()
    )
    stmt = select(
        func.count(),
        func.count().filter(open_mine.c.due_at < now),
        func.count().filter(open_mine.c.due_at >= now, open_mine.c.due_at < soon),
    ).select_from(open_mine)
    row = (await session.execute(stmt)).one()
    return int(row[0]), int(row[1]), int(row[2])
