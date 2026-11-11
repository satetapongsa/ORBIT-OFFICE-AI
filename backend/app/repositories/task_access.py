"""The one place that decides which tasks a user may see or manage (docs/SECURITY.md §3a).

A user sees a live (not soft-deleted) task when **any** of these holds:

1. they hold ``tasks:manage_all``;
2. they hold ``tasks:read_own`` and created the task or are one of its assignees;
3. they hold ``tasks:read_department`` or ``tasks:manage_department`` and the task belongs
   to their department.

They *manage* a task (edit, assign, delete) when they hold ``tasks:manage_all``, or hold
``tasks:manage_department`` and the task belongs to their department. The creator keeps
editing rights on their own task (see ``app.services.tasks.service.capabilities_for``).
"""

from __future__ import annotations

import uuid

from sqlalchemy import ColumnElement, false, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import P
from app.core.principal import CurrentUser
from app.models.task import Task, TaskAssignee

TASK_READ_PERMISSIONS = (
    P.TASKS_READ_OWN,
    P.TASKS_READ_DEPARTMENT,
    P.TASKS_MANAGE_DEPARTMENT,
    P.TASKS_MANAGE_ALL,
)


def can_read_tasks(user: CurrentUser) -> bool:
    return user.has_any(TASK_READ_PERMISSIONS)


def assigned_to(user_id: uuid.UUID) -> ColumnElement[bool]:
    return Task.id.in_(select(TaskAssignee.task_id).where(TaskAssignee.user_id == user_id))


def visible_tasks_condition(user: CurrentUser) -> ColumnElement[bool]:
    live = Task.deleted_at.is_(None)
    if user.has(P.TASKS_MANAGE_ALL):
        return live
    rules: list[ColumnElement[bool]] = []
    if user.has(P.TASKS_READ_OWN):
        rules.append(Task.created_by == user.id)
        rules.append(assigned_to(user.id))
    if user.department_id is not None and user.has_any(
        (P.TASKS_READ_DEPARTMENT, P.TASKS_MANAGE_DEPARTMENT)
    ):
        rules.append(Task.department_id == user.department_id)
    if not rules:
        return false()
    return live & or_(*rules)


def manages_department(user: CurrentUser, department_id: uuid.UUID | None) -> bool:
    """Whether ``user`` manages tasks that belong to ``department_id``."""
    if user.has(P.TASKS_MANAGE_ALL):
        return True
    return (
        user.has(P.TASKS_MANAGE_DEPARTMENT)
        and user.department_id is not None
        and department_id == user.department_id
    )


def managed_tasks_condition(user: CurrentUser) -> ColumnElement[bool]:
    if user.has(P.TASKS_MANAGE_ALL):
        return true()
    if user.has(P.TASKS_MANAGE_DEPARTMENT) and user.department_id is not None:
        return Task.department_id == user.department_id
    return false()


async def can_see_task(session: AsyncSession, user: CurrentUser, task_id: uuid.UUID) -> bool:
    stmt = select(Task.id).where(Task.id == task_id, visible_tasks_condition(user))
    return (await session.scalar(stmt)) is not None
