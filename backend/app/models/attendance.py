"""Attendance: daily check-in / check-out (ADR-069)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.identity import _in_check


class WorkMode(StrEnum):
    OFFICE = "OFFICE"
    WFH = "WFH"
    ONSITE = "ONSITE"


class AttendanceRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One row per person per local working date; times are database time."""

    __tablename__ = "attendance_records"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    check_in_at: Mapped[datetime] = mapped_column(nullable=False)
    check_out_at: Mapped[datetime | None] = mapped_column()
    work_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default=WorkMode.OFFICE.value
    )
    late: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    check_in_note: Mapped[str | None] = mapped_column(String(300))
    check_out_note: Mapped[str | None] = mapped_column(String(300))

    __table_args__ = (
        CheckConstraint(_in_check("work_mode", WorkMode), name="work_mode"),
        CheckConstraint("check_out_at IS NULL OR check_out_at >= check_in_at", name="time_order"),
        Index("uq_attendance_user_date", "user_id", "work_date", unique=True),
        Index("ix_attendance_work_date", "work_date"),
    )
