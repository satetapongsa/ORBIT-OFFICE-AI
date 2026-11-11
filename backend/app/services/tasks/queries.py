"""Read models for the task API (visibility via ``task_access`` in every query)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import PermissionDeniedError
from app.core.permissions import P
from app.core.principal import CurrentUser
from app.core.security import utcnow
from app.models.task import TaskStatus
from app.repositories import tasks as task_repo
from app.repositories.task_access import can_read_tasks
from app.repositories.tasks import TaskFilters, TaskRow
from app.schemas.documents import UserRef
from app.schemas.identity import DepartmentRef
from app.schemas.tasks import (
    AssignableUser,
    TaskAttachmentOut,
    TaskCommentOut,
    TaskDetail,
    TaskEventOut,
    TaskListItem,
    TaskPage,
    TaskSort,
)
from app.services.tasks.service import get_access

HISTORY_LIMIT = 200


def require_task_reader(user: CurrentUser) -> None:
    if not can_read_tasks(user):
        raise PermissionDeniedError("คุณไม่มีสิทธิ์ดูงาน")


def is_overdue(due_at: datetime | None, status: str, now: datetime) -> bool:
    return due_at is not None and due_at < now and TaskStatus(status).is_open


def _item(row: TaskRow, now: datetime) -> TaskListItem:
    task = row.task
    return TaskListItem(
        id=task.id,
        title=task.title,
        status=TaskStatus(task.status),
        priority=task.priority,
        due_at=task.due_at,
        is_overdue=is_overdue(task.due_at, task.status, now),
        department=DepartmentRef.model_validate(row.department) if row.department else None,
        created_by=UserRef(id=task.created_by, display_name=row.creator_name),
        assignees=[UserRef(id=uid, display_name=name) for uid, name in row.assignees],
        comment_count=row.comment_count,
        attachment_count=row.attachment_count,
        completed_at=task.completed_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


async def list_tasks(
    session: AsyncSession,
    user: CurrentUser,
    filters: TaskFilters,
    *,
    sort: TaskSort,
    page: int,
    page_size: int,
) -> TaskPage:
    require_task_reader(user)
    if filters.scope == "department" and not user.has_any(
        (P.TASKS_READ_DEPARTMENT, P.TASKS_MANAGE_DEPARTMENT, P.TASKS_MANAGE_ALL)
    ):
        raise PermissionDeniedError("คุณไม่มีสิทธิ์ดูงานของแผนก")
    now = utcnow()
    rows, total = await task_repo.list_tasks(
        session, user, filters, now=now, sort=sort, page=page, page_size=page_size
    )
    return TaskPage(
        items=[_item(r, now) for r in rows], total=total, page=page, page_size=page_size
    )


async def get_detail(session: AsyncSession, user: CurrentUser, task_id: uuid.UUID) -> TaskDetail:
    require_task_reader(user)
    access = await get_access(session, user, task_id)
    row = await task_repo.get_task(session, user, task_id)
    assert row is not None  # noqa: S101 - get_access just found it
    item = _item(row, utcnow())
    return TaskDetail(
        **item.model_dump(),
        description=access.task.description,
        capabilities=access.capabilities,
    )


async def list_comments(
    session: AsyncSession, user: CurrentUser, task_id: uuid.UUID
) -> list[TaskCommentOut]:
    require_task_reader(user)
    access = await get_access(session, user, task_id)
    return [
        TaskCommentOut(
            id=c.id,
            author=UserRef(id=c.author_id, display_name=name or "ผู้ใช้ที่ถูกลบ")
            if c.author_id
            else None,
            body=c.body,
            created_at=c.created_at,
            edited_at=c.edited_at,
            can_edit=c.author_id == user.id,
            can_delete=c.author_id == user.id or access.is_manager,
        )
        for c, name in await task_repo.list_comments(session, task_id)
    ]


async def list_attachments(
    session: AsyncSession, user: CurrentUser, task_id: uuid.UUID
) -> list[TaskAttachmentOut]:
    require_task_reader(user)
    access = await get_access(session, user, task_id)
    return [
        TaskAttachmentOut(
            id=a.id,
            original_filename=a.original_filename,
            file_type=a.file_type,
            size_bytes=a.size_bytes,
            uploaded_by=UserRef(id=a.uploaded_by, display_name=name or "ผู้ใช้ที่ถูกลบ")
            if a.uploaded_by
            else None,
            created_at=a.created_at,
            can_delete=a.uploaded_by == user.id or access.is_creator or access.is_manager,
        )
        for a, name in await task_repo.list_attachments(session, task_id)
    ]


async def list_events(
    session: AsyncSession, user: CurrentUser, task_id: uuid.UUID
) -> list[TaskEventOut]:
    require_task_reader(user)
    await get_access(session, user, task_id)
    return [
        TaskEventOut(
            id=e.id,
            event_type=e.event_type,
            actor=UserRef(id=e.actor_id, display_name=name or "ผู้ใช้ที่ถูกลบ") if e.actor_id else None,
            from_value=e.from_value,
            to_value=e.to_value,
            created_at=e.created_at,
        )
        for e, name in await task_repo.list_events(session, task_id, limit=HISTORY_LIMIT)
    ]


async def assignable_users(
    session: AsyncSession, user: CurrentUser, q: str | None, *, limit: int
) -> list[AssignableUser]:
    """People the caller may assign: anyone with ``tasks:manage_all``, otherwise their own
    department (only for holders of ``tasks:assign``); without it, only themself."""
    if user.has(P.TASKS_MANAGE_ALL):
        users = await task_repo.assignable_users(session, None, q, limit=limit)
    elif user.has(P.TASKS_ASSIGN) and user.department_id is not None:
        users = await task_repo.assignable_users(session, user.department_id, q, limit=limit)
    else:
        users = list(await task_repo.active_users(session, [user.id]))
    return [
        AssignableUser(
            id=u.id,
            display_name=u.display_name,
            job_title=u.job_title,
            department=DepartmentRef.model_validate(u.department) if u.department else None,
        )
        for u in users
    ]
