"""Tasks, assignees, comments, attachments and the per-task event timeline.

Visibility is decided by the single predicate in ``app.repositories.task_access``
(see docs/SECURITY.md §3a).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.identity import _in_check


class TaskStatus(StrEnum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    REVIEW = "REVIEW"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

    @property
    def is_open(self) -> bool:
        return self not in (TaskStatus.COMPLETED, TaskStatus.CANCELLED)


OPEN_TASK_STATUSES: tuple[str, ...] = tuple(s.value for s in TaskStatus if s.is_open)


class TaskPriority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"

    @property
    def rank(self) -> int:
        return list(TaskPriority).index(self)


class TaskEventType(StrEnum):
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    STATUS_CHANGED = "STATUS_CHANGED"
    ASSIGNED = "ASSIGNED"
    UNASSIGNED = "UNASSIGNED"
    COMMENTED = "COMMENTED"
    ATTACHMENT_ADDED = "ATTACHMENT_ADDED"
    ATTACHMENT_REMOVED = "ATTACHMENT_REMOVED"


class Task(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "tasks"

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=TaskStatus.TODO.value)
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TaskPriority.MEDIUM.value
    )
    due_at: Mapped[datetime | None] = mapped_column()
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # The team that owns the task; department managers manage tasks of their department.
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    completed_at: Mapped[datetime | None] = mapped_column()

    __table_args__ = (
        CheckConstraint(_in_check("status", TaskStatus), name="status"),
        CheckConstraint(_in_check("priority", TaskPriority), name="priority"),
        Index("ix_tasks_status_due_at", "status", "due_at"),
        Index("ix_tasks_department_id", "department_id"),
        Index("ix_tasks_created_by", "created_by"),
        Index("ix_tasks_updated_at", "updated_at"),
        Index(
            "ix_tasks_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
    )


class TaskAssignee(Base):
    __tablename__ = "task_assignees"

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_task_assignees_user_id", "user_id"),)


class TaskComment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "task_comments"

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column()

    __table_args__ = (
        CheckConstraint("char_length(body) BETWEEN 1 AND 5000", name="body_length"),
        Index("ix_task_comments_task_created", "task_id", "created_at"),
    )


class TaskAttachment(UUIDPrimaryKeyMixin, Base):
    """A file attached to a task; the object lives in storage under ``storage_key``."""

    __tablename__ = "task_attachments"

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    # Server-generated (tasks/{task_id}/{attachment_id}); never derived from user input.
    storage_key: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(150), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("file_type IN ('PDF', 'DOCX', 'XLSX', 'TXT')", name="file_type"),
        CheckConstraint("size_bytes >= 0", name="size_bytes"),
        Index("ix_task_attachments_task_id", "task_id"),
    )


class TaskEvent(UUIDPrimaryKeyMixin, Base):
    """User-visible task timeline (who changed what). Security events also go to audit_logs."""

    __tablename__ = "task_events"

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    from_value: Mapped[str | None] = mapped_column(String(300))
    to_value: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(_in_check("event_type", TaskEventType), name="event_type"),
        Index("ix_task_events_task_created", "task_id", "created_at"),
    )
