"""AI assistant schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.models.ai import ActionStatus

MAX_MESSAGE_CHARS = 4000

MessageText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_CHARS)
]
SessionTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class AiToolInfo(BaseModel):
    name: str
    label: str
    requires_confirmation: bool


class AiStatus(BaseModel):
    enabled: bool
    provider: str | None
    model: str | None
    tools: list[AiToolInfo]
    max_message_chars: int = MAX_MESSAGE_CHARS


class ChatSessionCreate(BaseModel):
    title: SessionTitle | None = None


class ChatSessionUpdate(BaseModel):
    title: SessionTitle


class ChatSessionOut(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    last_message_at: datetime


class ChatSessionPage(BaseModel):
    items: list[ChatSessionOut]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class ActionOut(BaseModel):
    id: uuid.UUID
    tool_name: str
    summary: str
    status: ActionStatus
    result: dict[str, Any] | None
    error: str | None
    expires_at: datetime
    decided_at: datetime | None
    created_at: datetime


class Citation(BaseModel):
    """A document passage the answer cites as [n]."""

    n: int
    document_id: uuid.UUID
    title: str
    page: int | None = None


class ChatMessageOut(BaseModel):
    """What the UI shows. Tool messages carry a label and outcome, never the raw tool data."""

    id: uuid.UUID
    role: Literal["user", "assistant", "tool", "system"]
    content: str
    tool_name: str | None = None
    tool_label: str | None = None
    tool_ok: bool | None = None
    action_id: uuid.UUID | None = None
    citations: list[Citation] = Field(default_factory=list)
    created_at: datetime


class ChatSessionDetail(ChatSessionOut):
    messages: list[ChatMessageOut]
    actions: list[ActionOut]


class SendMessage(BaseModel):
    content: MessageText
