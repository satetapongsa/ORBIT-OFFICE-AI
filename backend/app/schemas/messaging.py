"""Schemas for direct messages and personal notes (ADR-060)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

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


class ChatAttachmentOut(BaseModel):
    """A file in a chat (ADR-072). Download from ``/chat/attachments/{id}``."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    file_type: str
    mime_type: str
    size_bytes: int
    is_image: bool


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_id: uuid.UUID
    body: str
    created_at: datetime
    edited_at: datetime | None = None
    attachment: ChatAttachmentOut | None = None


class ConversationOut(BaseModel):
    id: uuid.UUID
    other: ChatPerson
    last_message: MessageOut | None
    last_message_at: datetime | None
    unread_count: int = Field(ge=0)
    # Read receipt: my messages up to this time have been seen by the other person.
    other_last_read_at: datetime | None
    other_typing: bool


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
    other_last_read_at: datetime | None = None
    other_typing: bool = False


class ChatEvents(BaseModel):
    """Long-poll answer: send ``version`` back as ``since``; a new value means "refetch"."""

    version: int


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


# --- Group chats (ADR-071) --------------------------------------------------------------

GroupName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class GroupCreate(BaseModel):
    name: GroupName
    member_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    # Adds every active member of this department (own department, or anyone with users:read).
    include_department_id: uuid.UUID | None = None


class GroupRename(BaseModel):
    name: GroupName


class GroupAddMembers(BaseModel):
    user_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


class GroupMember(BaseModel):
    id: uuid.UUID
    display_name: str
    department_name: str | None
    role: Literal["ADMIN", "MEMBER"]
    last_read_at: datetime | None


class GroupMessageOut(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    sender_id: uuid.UUID | None
    sender_name: str | None
    kind: Literal["TEXT", "SYSTEM"]
    body: str
    created_at: datetime
    edited_at: datetime | None
    attachment: ChatAttachmentOut | None = None


class GroupSummary(BaseModel):
    id: uuid.UUID
    name: str
    member_count: int
    my_role: Literal["ADMIN", "MEMBER"]
    last_message: GroupMessageOut | None
    last_message_at: datetime | None
    unread_count: int = Field(ge=0)
    typing_names: list[str]


class GroupDetail(GroupSummary):
    members: list[GroupMember]


class GroupMessagePage(BaseModel):
    items: list[GroupMessageOut]
    has_more: bool
    # For "อ่านแล้ว N คน" and "X กำลังพิมพ์…"
    reads: list[GroupMember]
    typing_names: list[str]
