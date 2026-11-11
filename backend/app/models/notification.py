"""In-app notifications addressed to a single user."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin
from app.models.identity import _in_check


class NotificationType(StrEnum):
    """Broad category, used by the UI to choose an icon. Later phases add TASK, TICKET, …"""

    SECURITY = "SECURITY"  # password changes, suspicious session activity
    ACCOUNT = "ACCOUNT"  # account created/updated, roles changed
    SYSTEM = "SYSTEM"  # announcements from the system itself


class Notification(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Relative in-app path only (validated by the service); never an external URL.
    link_url: Mapped[str | None] = mapped_column(String(500))
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[uuid.UUID | None] = mapped_column()
    read_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(_in_check("type", NotificationType), name="type"),
        CheckConstraint(
            "link_url IS NULL OR (link_url LIKE '/%' AND link_url NOT LIKE '//%')",
            name="link_url_relative",
        ),
        # Btree scans backwards, so this also serves "newest first" per user.
        Index("ix_notifications_user_read_created", "user_id", "read_at", "created_at"),
        Index(
            "ix_notifications_user_unread",
            "user_id",
            postgresql_where=text("read_at IS NULL"),
        ),
    )
