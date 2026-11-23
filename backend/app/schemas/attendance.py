"""Attendance schemas (ADR-069)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.models.attendance import WorkMode

Note = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]


class CheckIn(BaseModel):
    work_mode: WorkMode = WorkMode.OFFICE
    note: Note = ""


class CheckOut(BaseModel):
    note: Note = ""


class AttendanceOut(BaseModel):
    id: uuid.UUID
    work_date: date
    check_in_at: datetime
    check_out_at: datetime | None
    work_mode: WorkMode
    late: bool
    check_in_note: str | None
    check_out_note: str | None
    worked_minutes: int | None


class WorkHours(BaseModel):
    start: str
    end: str
    late_after: str


class TodayOut(BaseModel):
    date: date
    server_time: datetime
    hours: WorkHours
    record: AttendanceOut | None
    on_leave: str | None  # approved leave today, e.g. "ลาพักร้อน (ครึ่งเช้า)"


class MonthSummary(BaseModel):
    days_present: int
    late_days: int
    wfh_days: int
    total_minutes: int
    average_check_in: str | None  # "HH:MM" local time


class MyMonth(BaseModel):
    month: str  # YYYY-MM
    records: list[AttendanceOut]
    summary: MonthSummary


class TeamPerson(BaseModel):
    id: uuid.UUID
    display_name: str
    department_name: str | None
    job_title: str | None


class TeamDayRow(BaseModel):
    person: TeamPerson
    record: AttendanceOut | None
    on_leave: str | None


class TeamDay(BaseModel):
    date: date
    rows: list[TeamDayRow]
    present: int
    late: int
    on_leave: int
    missing: int


class MonthlyRow(BaseModel):
    person: TeamPerson
    days_present: int
    late_days: int
    wfh_days: int
    leave_days: float
    total_minutes: int


class MonthlyReport(BaseModel):
    month: str
    working_days: int
    rows: list[MonthlyRow]
