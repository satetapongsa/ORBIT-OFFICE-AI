"""Direct messages between two users, and private notes (ADR-060)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

MESSAGE_MAX_CHARS = 4000
NOTE_MAX_CHARS = 20000


class Conversation(UUIDPrimaryKeyMixin, Base):
    """One private thread per pair of users. ``user_low_id`` < ``user_high_id`` keeps it unique."""

    __tablename__ = "conversations"

    user_low_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    user_high_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    last_message_at: Mapped[datetime | None] = mapped_column()
    low_last_read_at: Mapped[datetime | None] = mapped_column()
    high_last_read_at: Mapped[datetime | None] = mapped_column()
    # Last "typing" signal of each participant (database time); shown for a few seconds.
    low_typing_at: Mapped[datetime | None] = mapped_column()
    high_typing_at: Mapped[datetime | None] = mapped_column()

    __table_args__ = (
        CheckConstraint("user_low_id < user_high_id", name="ordered_pair"),
        Index("uq_conversations_pair", "user_low_id", "user_high_id", unique=True),
        Index("ix_conversations_user_high_id", "user_high_id"),
    )

    def other_user_id(self, user_id: uuid.UUID) -> uuid.UUID:
        return self.user_high_id if user_id == self.user_low_id else self.user_low_id

    def last_read_at(self, user_id: uuid.UUID) -> datetime | None:
        return self.low_last_read_at if user_id == self.user_low_id else self.high_last_read_at

    def typing_at(self, user_id: uuid.UUID) -> datetime | None:
        return self.low_typing_at if user_id == self.user_low_id else self.high_typing_at

    def set_typing(self, user_id: uuid.UUID, when: object) -> None:
        """``when`` is a datetime, ``func.now()`` or ``None`` (stopped typing)."""
        if user_id == self.user_low_id:
            self.low_typing_at = when  # type: ignore[assignment]
        else:
            self.high_typing_at = when  # type: ignore[assignment]

    def mark_read(self, user_id: uuid.UUID, when: datetime) -> None:
        if user_id == self.user_low_id:
            self.low_last_read_at = when
        else:
            self.high_last_read_at = when


class DirectMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "direct_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column()

    __table_args__ = (
        CheckConstraint(f"char_length(body) BETWEEN 1 AND {MESSAGE_MAX_CHARS}", name="body_length"),
        Index("ix_direct_messages_conversation_created", "conversation_id", "created_at"),
    )


class Note(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A personal note. Only its owner can read it (administrators included)."""

    __tablename__ = "notes"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Changes only when the title or text changes (not when a summary is stored).
    content_updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_summary_at: Mapped[datetime | None] = mapped_column()

    __table_args__ = (
        CheckConstraint(f"char_length(content) <= {NOTE_MAX_CHARS}", name="content_length"),
        Index("ix_notes_owner_content_updated", "owner_id", "content_updated_at"),
    )
