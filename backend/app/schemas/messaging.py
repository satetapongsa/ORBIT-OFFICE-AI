"""Schemas for direct messages and personal notes (ADR-060)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.messaging import MESSAGE_MAX_CHARS, NOTE_MAX_CHARS

# --- Chat -------------------------------------------------------------------------------

MessageBody = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MESSAGE_MAX_CHARS)
]


class ChatPerson(BaseModel):
    id: uuid.UUID
    display_name: str
    job_title: str | None
    department_name: str | None
    is_active: bool


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_id: uuid.UUID
    body: str
    created_at: datetime


class ConversationOut(BaseModel):
    id: uuid.UUID
    other: ChatPerson
    last_message: MessageOut | None
    last_message_at: datetime | None
    unread_count: int = Field(ge=0)


class ConversationList(BaseModel):
    items: list[ConversationOut]
    unread_total: int = Field(ge=0)


class StartConversation(BaseModel):
    user_id: uuid.UUID


class SendMessage(BaseModel):
    body: MessageBody


class MessagePage(BaseModel):
    """Messages oldest-first; ``has_more`` means older messages exist before the first one."""

    items: list[MessageOut]
    has_more: bool


class ChatUnread(BaseModel):
    unread_total: int = Field(ge=0)


# --- Notes ------------------------------------------------------------------------------

NoteTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class NoteCreate(BaseModel):
    title: NoteTitle
    content: str = Field(default="", max_length=NOTE_MAX_CHARS)


class NoteUpdate(BaseModel):
    title: NoteTitle | None = None
    content: str | None = Field(default=None, max_length=NOTE_MAX_CHARS)


class NoteSummaryOut(BaseModel):
    """List item: the text is cut to a short preview."""

    id: uuid.UUID
    title: str
    preview: str
    has_summary: bool
    content_updated_at: datetime
    created_at: datetime


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    content: str
    ai_summary: str | None
    ai_summary_at: datetime | None
    # True when the text changed after the summary was written.
    summary_outdated: bool
    content_updated_at: datetime
    created_at: datetime
