"""Group chats (ADR-071)."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin
from app.models.identity import _in_check
from app.models.messaging import MESSAGE_MAX_CHARS

GROUP_MAX_MEMBERS = 200


class GroupRole(StrEnum):
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"


class GroupMessageKind(StrEnum):
    TEXT = "TEXT"
    SYSTEM = "SYSTEM"  # "A added B", "A left the group", ...


class ChatGroup(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "chat_groups"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    last_message_at: Mapped[datetime | None] = mapped_column()


class ChatGroupMember(Base):
    __tablename__ = "chat_group_members"

    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_groups.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(10), nullable=False, default=GroupRole.MEMBER.value)
    joined_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    last_read_at: Mapped[datetime | None] = mapped_column()
    typing_at: Mapped[datetime | None] = mapped_column()

    __table_args__ = (
        CheckConstraint(_in_check("role", GroupRole), name="role"),
        Index("ix_chat_group_members_user_id", "user_id"),
    )


class GroupMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "group_messages"

    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_groups.id", ondelete="CASCADE"), nullable=False
    )
    sender_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(
        String(10), nullable=False, default=GroupMessageKind.TEXT.value
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column()

    __table_args__ = (
        CheckConstraint(_in_check("kind", GroupMessageKind), name="kind"),
        CheckConstraint(f"char_length(body) BETWEEN 1 AND {MESSAGE_MAX_CHARS}", name="body_length"),
        Index("ix_group_messages_group_created", "group_id", "created_at"),
    )
