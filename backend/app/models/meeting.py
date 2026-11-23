"""Calendar meetings and invitations (ADR-070)."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.identity import _in_check


class MeetingResponse(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    TENTATIVE = "TENTATIVE"
    DECLINED = "DECLINED"


class Meeting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "meetings"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    location: Mapped[str | None] = mapped_column(String(200))
    online_url: Mapped[str | None] = mapped_column(String(500))
    start_at: Mapped[datetime] = mapped_column(nullable=False)
    end_at: Mapped[datetime] = mapped_column(nullable=False)
    organizer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reminder_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    reminder_sent_at: Mapped[datetime | None] = mapped_column()
    cancelled_at: Mapped[datetime | None] = mapped_column()

    __table_args__ = (
        CheckConstraint("end_at > start_at", name="time_order"),
        CheckConstraint("char_length(description) <= 5000", name="description_length"),
        CheckConstraint("reminder_minutes BETWEEN 0 AND 1440", name="reminder_range"),
        CheckConstraint(
            "online_url IS NULL OR online_url LIKE 'https://%'", name="online_url_https"
        ),
        Index("ix_meetings_start_at", "start_at"),
    )


class MeetingAttendee(Base):
    __tablename__ = "meeting_attendees"

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    response: Mapped[str] = mapped_column(
        String(10), nullable=False, default=MeetingResponse.PENDING.value
    )
    responded_at: Mapped[datetime | None] = mapped_column()

    __table_args__ = (
        CheckConstraint(_in_check("response", MeetingResponse), name="response"),
        Index("ix_meeting_attendees_user_id", "user_id"),
    )
