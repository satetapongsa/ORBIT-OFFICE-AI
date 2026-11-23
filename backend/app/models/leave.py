"""Leave (time off) requests (ADR-068)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.identity import _in_check


class LeaveStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class HalfDay(StrEnum):
    NONE = "NONE"
    MORNING = "MORNING"
    AFTERNOON = "AFTERNOON"


class LeaveType(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """``days_per_year`` NULL = no yearly limit (e.g. unpaid leave)."""

    __tablename__ = "leave_types"

    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    days_per_year: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="blue")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint("days_per_year IS NULL OR days_per_year >= 0", name="days_non_negative"),
    )


class LeaveQuota(Base):
    """Per-person override of a type's yearly days (set by HR)."""

    __tablename__ = "leave_quotas"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    leave_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leave_types.id", ondelete="CASCADE"), primary_key=True
    )
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    days: Mapped[Decimal] = mapped_column(Numeric(5, 1), nullable=False)

    __table_args__ = (CheckConstraint("days >= 0", name="days_non_negative"),)


class LeaveRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "leave_requests"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    leave_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leave_types.id", ondelete="RESTRICT"), nullable=False
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    half_day: Mapped[str] = mapped_column(String(10), nullable=False, default=HalfDay.NONE.value)
    days: Mapped[Decimal] = mapped_column(Numeric(5, 1), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default=LeaveStatus.PENDING.value
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column()
    decision_note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="date_order"),
        CheckConstraint("days > 0", name="days_positive"),
        CheckConstraint(_in_check("status", LeaveStatus), name="status"),
        CheckConstraint(_in_check("half_day", HalfDay), name="half_day"),
        CheckConstraint("half_day = 'NONE' OR start_date = end_date", name="half_day_single_date"),
        CheckConstraint("char_length(reason) <= 2000", name="reason_length"),
        Index("ix_leave_requests_user_start", "user_id", "start_date"),
        Index("ix_leave_requests_status", "status"),
        Index("ix_leave_requests_dates", "start_date", "end_date"),
    )


# Defaults follow the Thai Labour Protection Act minimums; HR can change them.
DEFAULT_LEAVE_TYPES: tuple[tuple[str, str, Decimal | None, str], ...] = (
    ("ANNUAL", "ลาพักร้อน", Decimal(6), "emerald"),
    ("SICK", "ลาป่วย", Decimal(30), "rose"),
    ("PERSONAL", "ลากิจ", Decimal(3), "amber"),
    ("MATERNITY", "ลาคลอด", Decimal(98), "violet"),
    ("UNPAID", "ลาไม่รับค่าจ้าง", None, "slate"),
)
