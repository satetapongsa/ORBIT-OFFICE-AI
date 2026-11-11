"""AI assistant: chat sessions, messages and proposed actions awaiting user confirmation.

Everything here belongs to one user; every query filters by ``user_id`` (owner-only, like
notifications). Message content written by the model or returned by tools is untrusted text.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.identity import _in_check


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"  # result of one tool call (linked by tool_call_id)
    SYSTEM = "system"  # notes from the application, e.g. "the user confirmed action X"


class ActionStatus(StrEnum):
    PENDING = "PENDING"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class ChatSession(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "chat_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    last_message_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_chat_sessions_user_last", "user_id", "last_message_at"),)


class ChatMessage(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "chat_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Assistant: [{id, name, arguments}] in provider-neutral form.
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    # Tool messages: which call this answers, the tool and the action it created (if any).
    tool_call_id: Mapped[str | None] = mapped_column(String(200))
    tool_name: Mapped[str | None] = mapped_column(String(100))
    action_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_action_requests.id", ondelete="SET NULL")
    )
    # Assistant: the provider's own content blocks, replayed unchanged to the same
    # provider/model (Claude thinking blocks must be passed back exactly as received).
    provider_payload: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    provider: Mapped[str | None] = mapped_column(String(50))
    model: Mapped[str | None] = mapped_column(String(200))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(_in_check("role", ChatRole), name="role"),
        Index("ix_chat_messages_session_created", "session_id", "created_at"),
    )


class AiActionRequest(UUIDPrimaryKeyMixin, Base):
    """A change the assistant proposed. Nothing runs until the user confirms it."""

    __tablename__ = "ai_action_requests"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_call_id: Mapped[str] = mapped_column(String(200), nullable=False)
    # Validated arguments (JSON-safe) — exactly what will run on confirmation.
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ActionStatus.PENDING.value
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(String(500))
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column()
    executed_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(_in_check("status", ActionStatus), name="status"),
        Index("ix_ai_action_requests_session", "session_id"),
        Index("ix_ai_action_requests_user_status", "user_id", "status"),
    )
