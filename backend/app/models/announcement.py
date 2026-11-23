"""Company announcements (ADR-067)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

ANNOUNCEMENT_BODY_MAX_CHARS = 10000


class Announcement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """``department_id`` NULL = whole company. Visible from ``published_at`` until
    ``expires_at`` (if set)."""

    __tablename__ = "announcements"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    important: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="CASCADE")
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    published_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column()

    __table_args__ = (
        CheckConstraint(
            f"char_length(body) BETWEEN 1 AND {ANNOUNCEMENT_BODY_MAX_CHARS}", name="body_length"
        ),
        CheckConstraint("expires_at IS NULL OR expires_at > published_at", name="expiry_order"),
        Index("ix_announcements_published", "published_at"),
        Index("ix_announcements_department_id", "department_id"),
    )


class AnnouncementRead(Base):
    __tablename__ = "announcement_reads"

    announcement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("announcements.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    read_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_announcement_reads_user_id", "user_id"),)
