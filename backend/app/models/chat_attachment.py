"""Files and images sent in direct messages and group chats (ADR-072)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKeyMixin

IMAGE_FILE_TYPES = frozenset({"PNG", "JPEG"})


class ChatAttachment(UUIDPrimaryKeyMixin, Base):
    """One stored file. Exactly one of ``conversation_id`` / ``group_id`` says who may open it;
    removing the chat removes the row (the object is then swept up by the daily clean-up)."""

    __tablename__ = "chat_attachments"

    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chat_groups.id", ondelete="CASCADE"), index=True
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    storage_key: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(150), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("num_nonnulls(conversation_id, group_id) = 1", name="one_chat"),
        CheckConstraint("size_bytes >= 0", name="size_bytes"),
    )

    @property
    def is_image(self) -> bool:
        return self.file_type in IMAGE_FILE_TYPES
