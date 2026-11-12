"""Task management endpoints (HTTP only — rules live in ``app.services.tasks``)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from fastapi.responses import StreamingResponse

from app.api.deps import (
    CurrentUserDep,
    DbDep,
    MetaDep,
    SettingsDep,
    get_document_storage,
    limit_uploads,
)
from app.api.v1.endpoints.documents import content_disposition
from app.models.task import TaskPriority, TaskStatus
from app.repositories.tasks import TaskFilters
from app.schemas.tasks import (
    AssignableUser,
    CommentIn,
    TaskAssigneesReplace,
    TaskAttachmentOut,
    TaskCommentOut,
    TaskCreate,
    TaskDetail,
    TaskEventOut,
    TaskPage,
    TaskScope,
    TaskSort,
    TaskStatusUpdate,
    TaskUpdate,
)
from app.services.tasks import queries
from app.services.tasks import service as task_service
from app.services.uploads import FileStorage

router = APIRouter(prefix="/tasks", tags=["tasks"])

StorageDep = Annotated[FileStorage, Depends(get_document_storage)]


@router.get("", response_model=TaskPage, summary="List tasks I can see")
async def list_tasks(
    db: DbDep,
    user: CurrentUserDep,
    scope: TaskScope = "all",
    q: Annotated[str | None, Query(max_length=200)] = None,
    status_: Annotated[TaskStatus | None, Query(alias="status")] = None,
    open_only: bool = False,
    priority: TaskPriority | None = None,
    assignee_id: uuid.UUID | None = None,
    overdue: bool = False,
    sort: TaskSort = "due",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> TaskPage:
    filters = TaskFilters(
        scope=scope,
        q=q,
        status=status_.value if status_ else None,
        open_only=open_only,
        priority=priority.value if priority else None,
        assignee_id=assignee_id,
        overdue=overdue,
    )
    return await queries.list_tasks(db, user, filters, sort=sort, page=page, page_size=page_size)


@router.post(
    "", response_model=TaskDetail, status_code=status.HTTP_201_CREATED, summary="Create a task"
)
async def create_task(
    body: TaskCreate, db: DbDep, user: CurrentUserDep, meta: MetaDep
) -> TaskDetail:
    task_id = await task_service.create_task(db, user, body, meta)
    return await queries.get_detail(db, user, task_id)


@router.get(
    "/assignable-users",
    response_model=list[AssignableUser],
    summary="People I may assign tasks to",
)
async def assignable_users(
    db: DbDep,
    user: CurrentUserDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[AssignableUser]:
    queries.require_task_reader(user)
    return await queries.assignable_users(db, user, q, limit=limit)


@router.get("/{task_id}", response_model=TaskDetail, summary="Task details")
async def get_task(task_id: uuid.UUID, db: DbDep, user: CurrentUserDep) -> TaskDetail:
    return await queries.get_detail(db, user, task_id)


@router.patch("/{task_id}", response_model=TaskDetail, summary="Edit a task")
async def update_task(
    task_id: uuid.UUID, body: TaskUpdate, db: DbDep, user: CurrentUserDep, meta: MetaDep
) -> TaskDetail:
    await task_service.update_task(db, user, task_id, body, meta)
    return await queries.get_detail(db, user, task_id)


@router.post("/{task_id}/status", response_model=TaskDetail, summary="Change the status")
async def change_status(
    task_id: uuid.UUID, body: TaskStatusUpdate, db: DbDep, user: CurrentUserDep, meta: MetaDep
) -> TaskDetail:
    await task_service.change_status(db, user, task_id, body.status, meta)
    return await queries.get_detail(db, user, task_id)


@router.put("/{task_id}/assignees", response_model=TaskDetail, summary="Replace assignees")
async def replace_assignees(
    task_id: uuid.UUID,
    body: TaskAssigneesReplace,
    db: DbDep,
    user: CurrentUserDep,
    meta: MetaDep,
) -> TaskDetail:
    await task_service.replace_assignees(db, user, task_id, body.user_ids, meta)
    return await queries.get_detail(db, user, task_id)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a task")
async def delete_task(
    task_id: uuid.UUID, db: DbDep, user: CurrentUserDep, meta: MetaDep
) -> Response:
    await task_service.delete_task(db, user, task_id, meta)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{task_id}/comments", response_model=list[TaskCommentOut], summary="Comments")
async def list_comments(
    task_id: uuid.UUID, db: DbDep, user: CurrentUserDep
) -> list[TaskCommentOut]:
    return await queries.list_comments(db, user, task_id)


@router.post(
    "/{task_id}/comments",
    response_model=list[TaskCommentOut],
    status_code=status.HTTP_201_CREATED,
    summary="Add a comment",
)
async def add_comment(
    task_id: uuid.UUID, body: CommentIn, db: DbDep, user: CurrentUserDep
) -> list[TaskCommentOut]:
    await task_service.add_comment(db, user, task_id, body.body)
    return await queries.list_comments(db, user, task_id)


@router.patch(
    "/{task_id}/comments/{comment_id}",
    response_model=list[TaskCommentOut],
    summary="Edit my comment",
)
async def edit_comment(
    task_id: uuid.UUID,
    comment_id: uuid.UUID,
    body: CommentIn,
    db: DbDep,
    user: CurrentUserDep,
) -> list[TaskCommentOut]:
    await task_service.edit_comment(db, user, task_id, comment_id, body.body)
    return await queries.list_comments(db, user, task_id)


@router.delete(
    "/{task_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a comment",
)
async def delete_comment(
    task_id: uuid.UUID, comment_id: uuid.UUID, db: DbDep, user: CurrentUserDep
) -> Response:
    await task_service.delete_comment(db, user, task_id, comment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{task_id}/attachments", response_model=list[TaskAttachmentOut], summary="Attachments")
async def list_attachments(
    task_id: uuid.UUID, db: DbDep, user: CurrentUserDep
) -> list[TaskAttachmentOut]:
    return await queries.list_attachments(db, user, task_id)


@router.post(
    "/{task_id}/attachments",
    response_model=list[TaskAttachmentOut],
    status_code=status.HTTP_201_CREATED,
    summary="Attach a file (PDF, DOCX, XLSX or TXT)",
    dependencies=[Depends(limit_uploads)],
)
async def add_attachment(
    task_id: uuid.UUID,
    db: DbDep,
    settings: SettingsDep,
    user: CurrentUserDep,
    meta: MetaDep,
    storage: StorageDep,
    file: Annotated[UploadFile, File(description="PDF, DOCX, XLSX or TXT")],
) -> list[TaskAttachmentOut]:
    await task_service.add_attachment(db, settings, storage, user, task_id, file, meta)
    return await queries.list_attachments(db, user, task_id)


@router.get(
    "/{task_id}/attachments/{attachment_id}/download",
    response_class=StreamingResponse,
    summary="Download an attachment",
)
async def download_attachment(
    task_id: uuid.UUID,
    attachment_id: uuid.UUID,
    db: DbDep,
    user: CurrentUserDep,
    meta: MetaDep,
    storage: StorageDep,
) -> StreamingResponse:
    attachment, stream = await task_service.open_attachment(
        db, storage, user, task_id, attachment_id, meta
    )
    return StreamingResponse(
        iter(stream),
        media_type=attachment.mime_type,
        headers={
            "Content-Disposition": content_disposition(attachment.original_filename),
            "Content-Length": str(attachment.size_bytes),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete(
    "/{task_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an attachment",
)
async def delete_attachment(
    task_id: uuid.UUID,
    attachment_id: uuid.UUID,
    db: DbDep,
    user: CurrentUserDep,
    meta: MetaDep,
    storage: StorageDep,
) -> Response:
    await task_service.delete_attachment(db, storage, user, task_id, attachment_id, meta)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{task_id}/history", response_model=list[TaskEventOut], summary="Task timeline")
async def list_events(task_id: uuid.UUID, db: DbDep, user: CurrentUserDep) -> list[TaskEventOut]:
    return await queries.list_events(db, user, task_id)
