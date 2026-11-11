"""Task management business rules.

Visibility is always decided by ``app.repositories.task_access`` (one SQL predicate);
capabilities are layered on top:

| operation                               | allowed for                                          |
| --------------------------------------- | ---------------------------------------------------- |
| see, comment, download attachments      | anyone who can see the task                          |
| create                                  | ``tasks:create`` (own department; other: manage_all) |
| assign someone other than yourself      | ``tasks:assign`` + (creator or manager of the task)  |
| edit title/description/priority/due     | creator or manager                                   |
| move to another department              | ``tasks:manage_all``                                 |
| change status (not cancel)              | creator, assignee or manager                         |
| cancel, delete (soft)                   | creator or manager                                   |
| add attachments                         | creator, assignee or manager                         |
| remove an attachment                    | its uploader, the creator or a manager               |
| edit / delete a comment                 | its author (delete: also a manager)                  |

"Manager" = ``tasks:manage_all``, or ``tasks:manage_department`` for tasks of your own
department. Without ``tasks:manage_all`` assignees must belong to the task's department.
Unknown and invisible tasks both answer 404.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from app.core.permissions import P
from app.core.principal import CurrentUser, RequestMeta
from app.core.security import utcnow
from app.core.storage import ObjectStream
from app.models.task import (
    Task,
    TaskAssignee,
    TaskAttachment,
    TaskComment,
    TaskEvent,
    TaskEventType,
    TaskStatus,
)
from app.repositories import departments as department_repo
from app.repositories import tasks as task_repo
from app.repositories.task_access import manages_department
from app.schemas.common import ErrorDetail
from app.schemas.tasks import TaskCapabilities, TaskCreate, TaskUpdate
from app.services import audit, notifications
from app.services.audit import AuditAction
from app.services.uploads import (
    FileStorage,
    discard_object,
    open_object,
    receive_upload,
    store_upload,
)

NOT_FOUND = "ไม่พบงาน หรือคุณไม่มีสิทธิ์เข้าถึง"
MAX_ATTACHMENTS = 20

STATUS_LABELS = {
    TaskStatus.TODO: "รอดำเนินการ",
    TaskStatus.IN_PROGRESS: "กำลังดำเนินการ",
    TaskStatus.REVIEW: "รอตรวจสอบ",
    TaskStatus.COMPLETED: "เสร็จสิ้น",
    TaskStatus.CANCELLED: "ยกเลิก",
}


@dataclass(frozen=True, slots=True)
class TaskAccess:
    task: Task
    assignee_ids: frozenset[uuid.UUID]
    is_creator: bool
    is_assignee: bool
    is_manager: bool
    capabilities: TaskCapabilities


def capabilities_for(
    user: CurrentUser, task: Task, assignee_ids: Iterable[uuid.UUID]
) -> TaskCapabilities:
    is_creator = task.created_by == user.id
    is_assignee = user.id in set(assignee_ids)
    is_manager = manages_department(user, task.department_id)
    owner_or_manager = is_creator or is_manager
    return TaskCapabilities(
        can_edit=owner_or_manager,
        can_change_status=owner_or_manager or is_assignee,
        can_cancel=owner_or_manager,
        can_assign=is_manager or (is_creator and user.has(P.TASKS_ASSIGN)),
        can_delete=owner_or_manager,
        can_comment=True,
        can_attach=owner_or_manager or is_assignee,
    )


async def get_access(session: AsyncSession, user: CurrentUser, task_id: uuid.UUID) -> TaskAccess:
    row = await task_repo.get_task(session, user, task_id)
    if row is None:
        raise NotFoundError(NOT_FOUND)
    ids = frozenset(uid for uid, _ in row.assignees)
    return TaskAccess(
        task=row.task,
        assignee_ids=ids,
        is_creator=row.task.created_by == user.id,
        is_assignee=user.id in ids,
        is_manager=manages_department(user, row.task.department_id),
        capabilities=capabilities_for(user, row.task, ids),
    )


def _deny(allowed: bool, message: str) -> None:
    if not allowed:
        raise PermissionDeniedError(message)


def _event(
    session: AsyncSession,
    task_id: uuid.UUID,
    actor_id: uuid.UUID,
    event_type: TaskEventType,
    *,
    from_value: str | None = None,
    to_value: str | None = None,
) -> None:
    session.add(
        TaskEvent(
            task_id=task_id,
            actor_id=actor_id,
            event_type=event_type.value,
            from_value=from_value[:300] if from_value else None,
            to_value=to_value[:300] if to_value else None,
        )
    )


async def _lock(session: AsyncSession, task_id: uuid.UUID) -> Task:
    task = await task_repo.get_task_for_update(session, task_id)
    if task is None:
        raise NotFoundError(NOT_FOUND)
    return task


async def _validate_assignees(
    session: AsyncSession,
    user: CurrentUser,
    department_id: uuid.UUID | None,
    user_ids: list[uuid.UUID],
) -> list[tuple[uuid.UUID, str]]:
    """Active users the actor may assign; returns (id, display name) in request order."""
    unique = list(dict.fromkeys(user_ids))
    found = {u.id: u for u in await task_repo.active_users(session, unique)}
    errors: list[ErrorDetail] = []
    for index, uid in enumerate(unique):
        target = found.get(uid)
        if target is None:
            errors.append(ErrorDetail(field=f"assignees.{index}", message="ไม่พบผู้ใช้นี้หรือบัญชีถูกระงับ"))
        elif (
            uid != user.id
            and not user.has(P.TASKS_MANAGE_ALL)
            and (department_id is None or target.department_id != department_id)
        ):
            errors.append(
                ErrorDetail(field=f"assignees.{index}", message="มอบหมายได้เฉพาะพนักงานในแผนกของงาน")
            )
    if errors:
        raise ValidationFailedError(details=errors)
    return [(uid, found[uid].display_name) for uid in unique]


async def _check_department(session: AsyncSession, department_id: uuid.UUID) -> None:
    if await department_repo.get_by_id(session, department_id) is None:
        raise ValidationFailedError(
            details=[ErrorDetail(field="department_id", message="ไม่พบแผนกนี้")]
        )


def _notify_watchers(recipients: Iterable[uuid.UUID], actor: CurrentUser) -> list[uuid.UUID]:
    return sorted({r for r in recipients if r != actor.id}, key=str)


# --- Commands -------------------------------------------------------------------------


async def create_task(
    session: AsyncSession, user: CurrentUser, data: TaskCreate, meta: RequestMeta
) -> uuid.UUID:
    _deny(user.has(P.TASKS_CREATE), "คุณไม่มีสิทธิ์สร้างงาน")
    department_id = data.department_id or user.department_id
    if department_id != user.department_id:
        _deny(user.has(P.TASKS_MANAGE_ALL), "สร้างงานได้เฉพาะในแผนกของคุณเอง")
    if department_id is not None:
        await _check_department(session, department_id)

    requested = data.assignee_ids or [user.id]
    if any(uid != user.id for uid in requested):
        _deny(user.has(P.TASKS_ASSIGN), "คุณไม่มีสิทธิ์มอบหมายงานให้ผู้อื่น")
    assignees = await _validate_assignees(session, user, department_id, requested)

    task = Task(
        title=data.title,
        description=data.description or None,
        priority=data.priority.value,
        due_at=data.due_at,
        created_by=user.id,
        department_id=department_id,
        status=TaskStatus.TODO.value,
    )
    session.add(task)
    await session.flush()
    _event(session, task.id, user.id, TaskEventType.CREATED, to_value=task.title)
    for uid, name in assignees:
        session.add(TaskAssignee(task_id=task.id, user_id=uid, assigned_by=user.id))
        _event(session, task.id, user.id, TaskEventType.ASSIGNED, to_value=name)
        if uid != user.id:
            notifications.task_assigned(
                session, uid, task_id=task.id, title=task.title, assigned_by=user.display_name
            )
    audit.record(
        session,
        AuditAction.TASK_CREATED,
        actor_id=user.id,
        meta=meta,
        entity_type="task",
        entity_id=task.id,
        details={"assignees": [str(uid) for uid, _ in assignees]},
    )
    await session.commit()
    return task.id


async def update_task(
    session: AsyncSession,
    user: CurrentUser,
    task_id: uuid.UUID,
    data: TaskUpdate,
    meta: RequestMeta,
) -> None:
    access = await get_access(session, user, task_id)
    _deny(access.capabilities.can_edit, "คุณไม่มีสิทธิ์แก้ไขงานนี้")
    changes = data.model_dump(exclude_unset=True)
    task = await _lock(session, task_id)

    changed: list[str] = []
    for name in ("title", "priority"):
        value = changes.get(name)
        if value is not None:
            value = value.value if hasattr(value, "value") else value
            if getattr(task, name) != value:
                setattr(task, name, value)
                changed.append(name)
    if "description" in changes:
        value = changes["description"] or None
        if task.description != value:
            task.description = value
            changed.append("description")
    if "due_at" in changes and task.due_at != changes["due_at"]:
        task.due_at = changes["due_at"]
        changed.append("due_at")
    if "department_id" in changes and changes["department_id"] != task.department_id:
        _deny(user.has(P.TASKS_MANAGE_ALL), "การย้ายงานไปแผนกอื่นต้องมีสิทธิ์จัดการงานทั้งหมด")
        if changes["department_id"] is not None:
            await _check_department(session, changes["department_id"])
        task.department_id = changes["department_id"]
        changed.append("department_id")
    if not changed:
        await session.rollback()
        return
    _event(session, task.id, user.id, TaskEventType.UPDATED, to_value=",".join(sorted(changed)))
    audit.record(
        session,
        AuditAction.TASK_UPDATED,
        actor_id=user.id,
        meta=meta,
        entity_type="task",
        entity_id=task.id,
        details={"fields": sorted(changed)},
    )
    await session.commit()


async def change_status(
    session: AsyncSession,
    user: CurrentUser,
    task_id: uuid.UUID,
    status: TaskStatus,
    meta: RequestMeta,
) -> None:
    access = await get_access(session, user, task_id)
    _deny(access.capabilities.can_change_status, "คุณไม่มีสิทธิ์เปลี่ยนสถานะงานนี้")
    if status is TaskStatus.CANCELLED:
        _deny(access.capabilities.can_cancel, "เฉพาะผู้สร้างงานหรือผู้จัดการเท่านั้นที่ยกเลิกงานได้")
    task = await _lock(session, task_id)
    previous = TaskStatus(task.status)
    if previous is status:
        await session.rollback()
        return
    task.status = status.value
    task.completed_at = utcnow() if status is TaskStatus.COMPLETED else None
    _event(
        session,
        task.id,
        user.id,
        TaskEventType.STATUS_CHANGED,
        from_value=previous.value,
        to_value=status.value,
    )
    for recipient in _notify_watchers([task.created_by, *access.assignee_ids], user):
        notifications.task_status_changed(
            session,
            recipient,
            task_id=task.id,
            title=task.title,
            status_label=STATUS_LABELS[status],
            changed_by=user.display_name,
        )
    audit.record(
        session,
        AuditAction.TASK_STATUS_CHANGED,
        actor_id=user.id,
        meta=meta,
        entity_type="task",
        entity_id=task.id,
        details={"from": previous.value, "to": status.value},
    )
    await session.commit()


async def replace_assignees(
    session: AsyncSession,
    user: CurrentUser,
    task_id: uuid.UUID,
    user_ids: list[uuid.UUID],
    meta: RequestMeta,
) -> None:
    access = await get_access(session, user, task_id)
    _deny(access.capabilities.can_assign, "คุณไม่มีสิทธิ์มอบหมายงานนี้")
    task = await _lock(session, task_id)
    wanted = await _validate_assignees(session, user, task.department_id, user_ids)
    wanted_ids = {uid for uid, _ in wanted}
    current = {link.user_id: link for link in await task_repo.assignee_links(session, task_id)}
    removed = [uid for uid in current if uid not in wanted_ids]
    added = [(uid, name) for uid, name in wanted if uid not in current]
    if not removed and not added:
        await session.rollback()
        return

    removed_names = await _names(session, removed)
    for uid in removed:
        await session.delete(current[uid])
        _event(session, task.id, user.id, TaskEventType.UNASSIGNED, from_value=removed_names[uid])
    for uid, name in added:
        session.add(TaskAssignee(task_id=task.id, user_id=uid, assigned_by=user.id))
        _event(session, task.id, user.id, TaskEventType.ASSIGNED, to_value=name)
        if uid != user.id:
            notifications.task_assigned(
                session, uid, task_id=task.id, title=task.title, assigned_by=user.display_name
            )
    task.updated_at = utcnow()
    audit.record(
        session,
        AuditAction.TASK_ASSIGNEES_CHANGED,
        actor_id=user.id,
        meta=meta,
        entity_type="task",
        entity_id=task.id,
        details={
            "added": [str(uid) for uid, _ in added],
            "removed": [str(uid) for uid in removed],
        },
    )
    await session.commit()


async def _names(session: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    from app.repositories import documents as document_repo

    names = await document_repo.user_names(session, set(ids))
    return {uid: names.get(uid, "ผู้ใช้ที่ถูกลบ") for uid in ids}


async def delete_task(
    session: AsyncSession, user: CurrentUser, task_id: uuid.UUID, meta: RequestMeta
) -> None:
    access = await get_access(session, user, task_id)
    _deny(access.capabilities.can_delete, "คุณไม่มีสิทธิ์ลบงานนี้")
    task = await _lock(session, task_id)
    task.deleted_at = utcnow()
    audit.record(
        session,
        AuditAction.TASK_DELETED,
        actor_id=user.id,
        meta=meta,
        entity_type="task",
        entity_id=task.id,
        details={"title": task.title},
    )
    await session.commit()


# --- Comments -------------------------------------------------------------------------


async def add_comment(
    session: AsyncSession, user: CurrentUser, task_id: uuid.UUID, body: str
) -> uuid.UUID:
    access = await get_access(session, user, task_id)
    comment = TaskComment(task_id=task_id, author_id=user.id, body=body)
    session.add(comment)
    await session.flush()
    _event(session, task_id, user.id, TaskEventType.COMMENTED)
    for recipient in _notify_watchers([access.task.created_by, *access.assignee_ids], user):
        notifications.task_commented(
            session,
            recipient,
            task_id=task_id,
            title=access.task.title,
            author=user.display_name,
            excerpt=body,
        )
    await session.commit()
    return comment.id


async def _comment(session: AsyncSession, task_id: uuid.UUID, comment_id: uuid.UUID) -> TaskComment:
    comment = await task_repo.get_comment(session, task_id, comment_id)
    if comment is None:
        raise NotFoundError("ไม่พบความคิดเห็นนี้")
    return comment


async def edit_comment(
    session: AsyncSession,
    user: CurrentUser,
    task_id: uuid.UUID,
    comment_id: uuid.UUID,
    body: str,
) -> None:
    await get_access(session, user, task_id)
    comment = await _comment(session, task_id, comment_id)
    _deny(comment.author_id == user.id, "แก้ไขได้เฉพาะความคิดเห็นของคุณเอง")
    if comment.body != body:
        comment.body = body
        comment.edited_at = utcnow()
    await session.commit()


async def delete_comment(
    session: AsyncSession, user: CurrentUser, task_id: uuid.UUID, comment_id: uuid.UUID
) -> None:
    access = await get_access(session, user, task_id)
    comment = await _comment(session, task_id, comment_id)
    _deny(
        comment.author_id == user.id or access.is_manager,
        "ลบได้เฉพาะความคิดเห็นของคุณเอง",
    )
    await session.delete(comment)
    await session.commit()


# --- Attachments ----------------------------------------------------------------------


async def add_attachment(
    session: AsyncSession,
    settings: Settings,
    storage: FileStorage,
    user: CurrentUser,
    task_id: uuid.UUID,
    upload: UploadFile,
    meta: RequestMeta,
) -> None:
    access = await get_access(session, user, task_id)
    _deny(access.capabilities.can_attach, "คุณไม่มีสิทธิ์แนบไฟล์ในงานนี้")
    if await task_repo.count_attachments(session, task_id) >= MAX_ATTACHMENTS:
        raise ConflictError(f"แนบไฟล์ได้สูงสุด {MAX_ATTACHMENTS} ไฟล์ต่องาน")
    stored = await receive_upload(upload, settings)
    attachment_id = uuid.uuid4()
    key = f"tasks/{task_id}/{attachment_id}"
    await store_upload(storage, key, upload, stored)
    try:
        await _lock(session, task_id)
        session.add(
            TaskAttachment(
                id=attachment_id,
                task_id=task_id,
                storage_key=key,
                original_filename=stored.inspected.filename,
                file_type=stored.inspected.file_type.value,
                mime_type=stored.inspected.mime_type,
                size_bytes=stored.size_bytes,
                sha256=stored.sha256,
                uploaded_by=user.id,
            )
        )
        _event(
            session,
            task_id,
            user.id,
            TaskEventType.ATTACHMENT_ADDED,
            to_value=stored.inspected.filename,
        )
        audit.record(
            session,
            AuditAction.TASK_ATTACHMENT_ADDED,
            actor_id=user.id,
            meta=meta,
            entity_type="task",
            entity_id=task_id,
            details={
                "filename": stored.inspected.filename,
                "file_type": stored.inspected.file_type.value,
                "size_bytes": stored.size_bytes,
            },
        )
        await session.commit()
    except Exception:
        await session.rollback()
        await discard_object(storage, key)
        raise


async def delete_attachment(
    session: AsyncSession,
    storage: FileStorage,
    user: CurrentUser,
    task_id: uuid.UUID,
    attachment_id: uuid.UUID,
    meta: RequestMeta,
) -> None:
    access = await get_access(session, user, task_id)
    attachment = await task_repo.get_attachment(session, task_id, attachment_id)
    if attachment is None:
        raise NotFoundError("ไม่พบไฟล์แนบนี้")
    _deny(
        attachment.uploaded_by == user.id or access.is_creator or access.is_manager,
        "คุณไม่มีสิทธิ์ลบไฟล์แนบนี้",
    )
    key, filename = attachment.storage_key, attachment.original_filename
    await session.delete(attachment)
    _event(session, task_id, user.id, TaskEventType.ATTACHMENT_REMOVED, from_value=filename)
    audit.record(
        session,
        AuditAction.TASK_ATTACHMENT_REMOVED,
        actor_id=user.id,
        meta=meta,
        entity_type="task",
        entity_id=task_id,
        details={"filename": filename},
    )
    await session.commit()
    # The row is gone; the object is removed after the commit (a failure only leaves an orphan).
    await discard_object(storage, key)


async def open_attachment(
    session: AsyncSession,
    storage: FileStorage,
    user: CurrentUser,
    task_id: uuid.UUID,
    attachment_id: uuid.UUID,
    meta: RequestMeta,
) -> tuple[TaskAttachment, ObjectStream]:
    await get_access(session, user, task_id)
    attachment = await task_repo.get_attachment(session, task_id, attachment_id)
    if attachment is None:
        raise NotFoundError("ไม่พบไฟล์แนบนี้")
    stream = await open_object(storage, attachment.storage_key)
    audit.record(
        session,
        AuditAction.TASK_ATTACHMENT_DOWNLOADED,
        actor_id=user.id,
        meta=meta,
        entity_type="task",
        entity_id=task_id,
        details={"filename": attachment.original_filename},
    )
    await session.commit()
    return attachment, stream
