"""Task management schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints

from app.models.document import FileType
from app.models.task import TaskEventType, TaskPriority, TaskStatus
from app.schemas.documents import UserRef
from app.schemas.identity import DepartmentRef

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=10_000)]
CommentBody = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)
]

MAX_ASSIGNEES = 20

TaskScope = Literal["all", "assigned", "created", "department"]
TaskSort = Literal["due", "updated", "created", "priority"]


class TaskCreate(BaseModel):
    title: Title
    description: Description | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    due_at: AwareDatetime | None = None
    # Empty = assigned to the creator. Assigning anyone else needs ``tasks:assign``.
    assignee_ids: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_ASSIGNEES)
    # Defaults to the creator's department; another department needs ``tasks:manage_all``.
    department_id: uuid.UUID | None = None


class TaskUpdate(BaseModel):
    title: Title | None = None
    description: Description | None = None
    priority: TaskPriority | None = None
    due_at: AwareDatetime | None = None
    department_id: uuid.UUID | None = None


class TaskStatusUpdate(BaseModel):
    status: TaskStatus


class TaskAssigneesReplace(BaseModel):
    user_ids: list[uuid.UUID] = Field(max_length=MAX_ASSIGNEES)


class CommentIn(BaseModel):
    body: CommentBody


class TaskCapabilities(BaseModel):
    can_edit: bool
    can_change_status: bool
    can_cancel: bool
    can_assign: bool
    can_delete: bool
    can_comment: bool
    can_attach: bool


class TaskListItem(BaseModel):
    id: uuid.UUID
    title: str
    status: TaskStatus
    priority: TaskPriority
    due_at: datetime | None
    is_overdue: bool
    department: DepartmentRef | None
    created_by: UserRef
    assignees: list[UserRef]
    comment_count: int = Field(ge=0)
    attachment_count: int = Field(ge=0)
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TaskDetail(TaskListItem):
    description: str | None
    capabilities: TaskCapabilities


class TaskPage(BaseModel):
    items: list[TaskListItem]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class TaskCommentOut(BaseModel):
    id: uuid.UUID
    author: UserRef | None
    body: str
    created_at: datetime
    edited_at: datetime | None
    can_edit: bool
    can_delete: bool


class TaskAttachmentOut(BaseModel):
    id: uuid.UUID
    original_filename: str
    file_type: FileType
    size_bytes: int
    uploaded_by: UserRef | None
    created_at: datetime
    can_delete: bool


class TaskEventOut(BaseModel):
    id: uuid.UUID
    event_type: TaskEventType
    actor: UserRef | None
    from_value: str | None
    to_value: str | None
    created_at: datetime


class AssignableUser(BaseModel):
    """Directory-safe fields for the assignee picker."""

    id: uuid.UUID
    display_name: str
    job_title: str | None
    department: DepartmentRef | None
