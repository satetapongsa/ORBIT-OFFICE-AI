"""Announcement schemas (ADR-067)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.models.announcement import ANNOUNCEMENT_BODY_MAX_CHARS

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Body = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=ANNOUNCEMENT_BODY_MAX_CHARS),
]


class AnnouncementCreate(BaseModel):
    title: Title
    body: Body
    important: bool = False
    pinned: bool = False
    department_id: uuid.UUID | None = None  # None = whole company
    expires_at: datetime | None = None
    notify: bool = True  # send an in-app notification to everyone who can see it


class AnnouncementUpdate(BaseModel):
    title: Title | None = None
    body: Body | None = None
    important: bool | None = None
    pinned: bool | None = None
    department_id: uuid.UUID | None = None
    expires_at: datetime | None = None
    # Explicit flags, because None also means "unchanged" for the two fields above.
    whole_company: bool = False
    clear_expiry: bool = False


class AnnouncementOut(BaseModel):
    id: uuid.UUID
    title: str
    body: str
    important: bool
    pinned: bool
    department_id: uuid.UUID | None
    department_name: str | None
    author_name: str | None
    published_at: datetime
    expires_at: datetime | None
    expired: bool
    edited: bool
    is_read: bool
    # Only for people who manage announcements: how many in the audience have read it.
    read_count: int | None = None
    audience_count: int | None = None


class AnnouncementList(BaseModel):
    items: list[AnnouncementOut]
    unread_count: int = Field(ge=0)


class AnnouncementUnread(BaseModel):
    unread_count: int = Field(ge=0)
