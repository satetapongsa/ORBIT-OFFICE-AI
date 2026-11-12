"""IT helpdesk: tickets, comments and attachments (public or internal) and the timeline."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Sequence,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.identity import _in_check
from app.models.task import TaskPriority

# Human-readable numbers (IT-2026-000123) come from this sequence.
ticket_number_seq = Sequence("ticket_number_seq", metadata=Base.metadata)


class TicketCategory(StrEnum):
    COMPUTER = "COMPUTER"
    NETWORK = "NETWORK"
    PRINTER = "PRINTER"
    SOFTWARE = "SOFTWARE"
    ACCOUNT_ACCESS = "ACCOUNT_ACCESS"
    OTHER = "OTHER"


class TicketStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"

    @property
    def is_open(self) -> bool:
        return self in (
            TicketStatus.OPEN,
            TicketStatus.IN_PROGRESS,
            TicketStatus.WAITING_FOR_USER,
        )


OPEN_TICKET_STATUSES: tuple[str, ...] = tuple(s.value for s in TicketStatus if s.is_open)


class TicketEventType(StrEnum):
    CREATED = "CREATED"
    STATUS_CHANGED = "STATUS_CHANGED"
    ASSIGNED = "ASSIGNED"
    UNASSIGNED = "UNASSIGNED"
    PRIORITY_CHANGED = "PRIORITY_CHANGED"
    CATEGORY_CHANGED = "CATEGORY_CHANGED"
    COMMENTED = "COMMENTED"
    ATTACHMENT_ADDED = "ATTACHMENT_ADDED"
    ATTACHMENT_REMOVED = "ATTACHMENT_REMOVED"


# Documents' four formats plus PNG/JPEG screenshots (see app.models.document.ImageType).
TICKET_ATTACHMENT_TYPES: tuple[str, ...] = ("PDF", "DOCX", "XLSX", "TXT", "PNG", "JPEG")


class Ticket(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "tickets"

    ticket_number: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TaskPriority.MEDIUM.value
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default=TicketStatus.OPEN.value)
    requester_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None] = mapped_column()
    closed_at: Mapped[datetime | None] = mapped_column()

    __table_args__ = (
        CheckConstraint(_in_check("category", TicketCategory), name="category"),
        CheckConstraint(_in_check("priority", TaskPriority), name="priority"),
        CheckConstraint(_in_check("status", TicketStatus), name="status"),
        Index("ix_tickets_requester_id", "requester_id"),
        Index("ix_tickets_assignee_status", "assignee_id", "status"),
        Index("ix_tickets_status_created", "status", "created_at"),
        Index(
            "ix_tickets_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
    )


class TicketComment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ticket_comments"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Internal notes are visible only with ``tickets:comment_internal`` (the IT team).
    is_internal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("char_length(body) BETWEEN 1 AND 5000", name="body_length"),
        Index("ix_ticket_comments_ticket_created", "ticket_id", "created_at"),
    )


class TicketEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ticket_events"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    from_value: Mapped[str | None] = mapped_column(String(300))
    to_value: Mapped[str | None] = mapped_column(String(300))
    is_internal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(_in_check("event_type", TicketEventType), name="event_type"),
        Index("ix_ticket_events_ticket_created", "ticket_id", "created_at"),
    )


class TicketAttachment(UUIDPrimaryKeyMixin, Base):
    """A file attached to a ticket; the object lives in storage under ``storage_key``."""

    __tablename__ = "ticket_attachments"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False
    )
    # Server-generated (tickets/{ticket_id}/{attachment_id}); never derived from user input.
    storage_key: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(150), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # Internal files (e.g. logs, vendor quotes) are visible only to the IT team, like notes.
    is_internal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "file_type IN (" + ", ".join(f"'{t}'" for t in TICKET_ATTACHMENT_TYPES) + ")",
            name="file_type",
        ),
        CheckConstraint("size_bytes >= 0", name="size_bytes"),
        Index("ix_ticket_attachments_ticket_created", "ticket_id", "created_at"),
    )
