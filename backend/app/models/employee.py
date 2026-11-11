"""Sensitive HR data, split from ``users`` so directory queries can never select it."""

from __future__ import annotations

import uuid
from datetime import date
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, Date, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.identity import _in_check


class EmploymentType(StrEnum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    CONTRACT = "CONTRACT"
    INTERN = "INTERN"


class EmployeeHrProfile(TimestampMixin, Base):
    """Readable only with ``employees:read_sensitive`` (or by the employee themself).

    Only the last four digits of the national ID are stored, never the full number.
    """

    __tablename__ = "employee_hr_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    national_id_last4: Mapped[str | None] = mapped_column(String(4))
    personal_phone: Mapped[str | None] = mapped_column(String(50))
    personal_email: Mapped[str | None] = mapped_column(String(320))
    address: Mapped[str | None] = mapped_column(Text)
    hire_date: Mapped[date | None] = mapped_column(Date)
    employment_type: Mapped[str | None] = mapped_column(String(20))
    emergency_contact: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    __table_args__ = (
        CheckConstraint(
            "national_id_last4 IS NULL OR national_id_last4 ~ '^[0-9]{4}$'",
            name="national_id_last4",
        ),
        CheckConstraint(
            "employment_type IS NULL OR " + _in_check("employment_type", EmploymentType),
            name="employment_type",
        ),
    )
