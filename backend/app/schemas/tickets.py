"""IT helpdesk schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.models.task import TaskPriority
from app.models.ticket import TicketCategory, TicketEventType, TicketStatus
from app.schemas.documents import UserRef

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Body = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]

TicketScope = Literal["mine", "assigned", "unassigned", "all"]
TicketSort = Literal["updated", "created", "priority"]


class TicketCreate(BaseModel):
    title: Title
    description: Body
    category: TicketCategory = TicketCategory.OTHER
    priority: TaskPriority = TaskPriority.MEDIUM


class TicketUpdate(BaseModel):
    category: TicketCategory | None = None
    priority: TaskPriority | None = None


class TicketStatusUpdate(BaseModel):
    status: TicketStatus


class TicketAssign(BaseModel):
    assignee_id: uuid.UUID | None


class TicketCommentIn(BaseModel):
    body: Body
    is_internal: bool = False


class TicketCapabilities(BaseModel):
    can_manage: bool
    can_assign: bool
    can_comment: bool
    can_comment_internal: bool
    allowed_statuses: list[TicketStatus]


class TicketListItem(BaseModel):
    id: uuid.UUID
    ticket_number: str
    title: str
    category: TicketCategory
    priority: TaskPriority
    status: TicketStatus
    requester: UserRef
    assignee: UserRef | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    closed_at: datetime | None


class TicketDetail(TicketListItem):
    description: str
    capabilities: TicketCapabilities


class TicketPage(BaseModel):
    items: list[TicketListItem]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class TicketCommentOut(BaseModel):
    id: uuid.UUID
    author: UserRef | None
    body: str
    is_internal: bool
    created_at: datetime


class TicketEventOut(BaseModel):
    id: uuid.UUID
    event_type: TicketEventType
    actor: UserRef | None
    from_value: str | None
    to_value: str | None
    is_internal: bool
    created_at: datetime
