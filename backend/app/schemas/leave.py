"""Leave schemas (ADR-068)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.models.leave import HalfDay, LeaveStatus


class LeaveTypeOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    days_per_year: Decimal | None
    color: str
    is_active: bool


class LeaveTypeUpdate(BaseModel):
    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
        | None
    ) = None
    days_per_year: Decimal | None = Field(default=None, ge=0, le=365)
    unlimited: bool = False  # set days_per_year to "no limit"
    is_active: bool | None = None


class LeaveBalance(BaseModel):
    leave_type: LeaveTypeOut
    year: int
    quota: Decimal | None  # None = no limit
    used: Decimal
    pending: Decimal
    remaining: Decimal | None


class LeaveRequestCreate(BaseModel):
    leave_type_id: uuid.UUID
    start_date: date
    end_date: date
    half_day: HalfDay = HalfDay.NONE
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] = ""


class LeaveDecision(BaseModel):
    approve: bool
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] = ""


class LeavePerson(BaseModel):
    id: uuid.UUID
    display_name: str
    department_name: str | None


class LeaveRequestOut(BaseModel):
    id: uuid.UUID
    person: LeavePerson
    leave_type: LeaveTypeOut
    start_date: date
    end_date: date
    half_day: HalfDay
    days: Decimal
    reason: str
    status: LeaveStatus
    decided_by_name: str | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime
    can_decide: bool
    can_cancel: bool


class MyLeave(BaseModel):
    year: int
    balances: list[LeaveBalance]
    requests: list[LeaveRequestOut]


class LeavePreview(BaseModel):
    days: Decimal


class QuotaUpdate(BaseModel):
    user_id: uuid.UUID
    leave_type_id: uuid.UUID
    year: int = Field(ge=2000, le=2100)
    days: Decimal | None = Field(default=None, ge=0, le=365)  # None = back to the type default


LeaveScope = Literal["approvals", "department", "all"]
