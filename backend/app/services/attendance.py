"""Attendance: check-in / check-out with server time (ADR-069).

* Times come from the database clock; the local working date and "late" use APP_TIMEZONE and
  WORK_START_TIME + LATE_GRACE_MINUTES.
* One record per person per local date; check-out only after check-in, once.
* Managers (``attendance:read_department``) see their department, HR (``attendance:read_all``)
  everyone: a daily board that also shows approved leave, and a monthly summary (also CSV).
"""

from __future__ import annotations

import csv
import io
import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ConflictError, PermissionDeniedError, ValidationFailedError
from app.core.permissions import P
from app.core.principal import CurrentUser, RequestMeta
from app.models.attendance import AttendanceRecord, WorkMode
from app.models.identity import User
from app.models.leave import HalfDay, LeaveRequest, LeaveStatus, LeaveType
from app.schemas.attendance import (
    AttendanceOut,
    CheckIn,
    CheckOut,
    MonthlyReport,
    MonthlyRow,
    MonthSummary,
    MyMonth,
    TeamDay,
    TeamDayRow,
    TeamPerson,
    TodayOut,
    WorkHours,
)
from app.schemas.common import ErrorDetail
from app.services import audit
from app.services.audit import AuditAction
from app.services.leave import working_days

HALF_TEXT = {HalfDay.MORNING.value: " (ครึ่งเช้า)", HalfDay.AFTERNOON.value: " (ครึ่งบ่าย)"}


def _hhmm(value: str) -> tuple[int, int]:
    hour, minute = value.split(":")
    return int(hour), int(minute)


def hours(settings: Settings) -> WorkHours:
    h, m = _hhmm(settings.work_start_time)
    late = datetime(2000, 1, 1, h, m) + timedelta(minutes=settings.late_grace_minutes)
    return WorkHours(
        start=settings.work_start_time, end=settings.work_end_time, late_after=f"{late:%H:%M}"
    )


async def _now(session: AsyncSession, settings: Settings) -> datetime:
    now = await session.scalar(select(func.now()))
    assert isinstance(now, datetime)  # noqa: S101
    return now.astimezone(ZoneInfo(settings.app_timezone))


def is_late(local: datetime, settings: Settings) -> bool:
    h, m = _hhmm(settings.work_start_time)
    limit = local.replace(hour=h, minute=m, second=0, microsecond=0) + timedelta(
        minutes=settings.late_grace_minutes
    )
    return local > limit


def _out(r: AttendanceRecord) -> AttendanceOut:
    minutes = (
        int((r.check_out_at - r.check_in_at).total_seconds() // 60) if r.check_out_at else None
    )
    return AttendanceOut(
        id=r.id,
        work_date=r.work_date,
        check_in_at=r.check_in_at,
        check_out_at=r.check_out_at,
        work_mode=WorkMode(r.work_mode),
        late=r.late,
        check_in_note=r.check_in_note,
        check_out_note=r.check_out_note,
        worked_minutes=minutes,
    )


async def _leave_on(
    session: AsyncSession, user_ids: Sequence[uuid.UUID], day: date
) -> dict[uuid.UUID, str]:
    if not user_ids:
        return {}
    rows = (
        await session.execute(
            select(LeaveRequest.user_id, LeaveType.name, LeaveRequest.half_day)
            .join(LeaveType, LeaveType.id == LeaveRequest.leave_type_id)
            .where(
                LeaveRequest.user_id.in_(user_ids),
                LeaveRequest.status == LeaveStatus.APPROVED.value,
                LeaveRequest.start_date <= day,
                LeaveRequest.end_date >= day,
            )
        )
    ).all()
    return {uid: name + HALF_TEXT.get(half, "") for uid, name, half in rows}


async def _today_record(
    session: AsyncSession, user_id: uuid.UUID, day: date, *, lock: bool = False
) -> AttendanceRecord | None:
    stmt = select(AttendanceRecord).where(
        AttendanceRecord.user_id == user_id, AttendanceRecord.work_date == day
    )
    return await session.scalar(stmt.with_for_update() if lock else stmt)


async def today(session: AsyncSession, user: CurrentUser, settings: Settings) -> TodayOut:
    now = await _now(session, settings)
    record = await _today_record(session, user.id, now.date())
    leave = await _leave_on(session, [user.id], now.date())
    return TodayOut(
        date=now.date(),
        server_time=now,
        hours=hours(settings),
        record=_out(record) if record else None,
        on_leave=leave.get(user.id),
    )


async def check_in(
    session: AsyncSession, user: CurrentUser, settings: Settings, data: CheckIn, meta: RequestMeta
) -> TodayOut:
    now = await _now(session, settings)
    if await _today_record(session, user.id, now.date()) is not None:
        raise ConflictError("วันนี้ลงเวลาเข้างานไปแล้ว")
    record = AttendanceRecord(
        user_id=user.id,
        work_date=now.date(),
        check_in_at=now,
        work_mode=data.work_mode.value,
        late=is_late(now, settings),
        check_in_note=data.note or None,
    )
    session.add(record)
    await session.flush()
    audit.record(
        session,
        AuditAction.ATTENDANCE_CHECK_IN,
        actor_id=user.id,
        meta=meta,
        entity_type="attendance",
        entity_id=record.id,
        details={"mode": data.work_mode.value, "late": record.late},
    )
    await session.commit()
    return await today(session, user, settings)


async def check_out(
    session: AsyncSession, user: CurrentUser, settings: Settings, data: CheckOut, meta: RequestMeta
) -> TodayOut:
    now = await _now(session, settings)
    record = await _today_record(session, user.id, now.date(), lock=True)
    if record is None:
        raise ConflictError("วันนี้ยังไม่ได้ลงเวลาเข้างาน")
    if record.check_out_at is not None:
        raise ConflictError("วันนี้ลงเวลาออกงานไปแล้ว")
    record.check_out_at = now
    record.check_out_note = data.note or None
    audit.record(
        session,
        AuditAction.ATTENDANCE_CHECK_OUT,
        actor_id=user.id,
        meta=meta,
        entity_type="attendance",
        entity_id=record.id,
    )
    await session.commit()
    return await today(session, user, settings)


def _month_range(month: str | None, now: date) -> tuple[str, date, date]:
    if month is None:
        first = now.replace(day=1)
    else:
        try:
            year, mon = (int(x) for x in month.split("-"))
            first = date(year, mon, 1)
        except ValueError:
            raise ValidationFailedError(
                details=[ErrorDetail(field="month", message="รูปแบบเดือนต้องเป็น YYYY-MM")]
            ) from None
    last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return f"{first:%Y-%m}", first, last


def _summary(records: Sequence[AttendanceRecord], settings: Settings) -> MonthSummary:
    tz = ZoneInfo(settings.app_timezone)
    minutes = [
        (r.check_in_at.astimezone(tz).hour * 60 + r.check_in_at.astimezone(tz).minute)
        for r in records
    ]
    average = None
    if minutes:
        avg = round(sum(minutes) / len(minutes))
        average = f"{avg // 60:02d}:{avg % 60:02d}"
    return MonthSummary(
        days_present=len(records),
        late_days=sum(1 for r in records if r.late),
        wfh_days=sum(1 for r in records if r.work_mode == WorkMode.WFH.value),
        total_minutes=sum(
            int((r.check_out_at - r.check_in_at).total_seconds() // 60)
            for r in records
            if r.check_out_at
        ),
        average_check_in=average,
    )


async def my_month(
    session: AsyncSession, user: CurrentUser, settings: Settings, month: str | None
) -> MyMonth:
    now = await _now(session, settings)
    label, first, last = _month_range(month, now.date())
    records = (
        await session.scalars(
            select(AttendanceRecord)
            .where(
                AttendanceRecord.user_id == user.id,
                AttendanceRecord.work_date.between(first, last),
            )
            .order_by(AttendanceRecord.work_date.desc())
        )
    ).all()
    return MyMonth(
        month=label, records=[_out(r) for r in records], summary=_summary(records, settings)
    )


def _scope(user: CurrentUser, department_id: uuid.UUID | None) -> ColumnElement[bool]:
    live = and_(User.is_active.is_(True), User.deleted_at.is_(None))
    if user.has(P.ATTENDANCE_READ_ALL):
        return live if department_id is None else and_(live, User.department_id == department_id)
    if user.has(P.ATTENDANCE_READ_DEPARTMENT) and user.department_id is not None:
        if department_id is not None and department_id != user.department_id:
            raise PermissionDeniedError("ดูได้เฉพาะแผนกของคุณ")
        return and_(live, User.department_id == user.department_id)
    raise PermissionDeniedError("คุณไม่มีสิทธิ์ดูเวลาเข้า-ออกงานของผู้อื่น")


def _person(u: User) -> TeamPerson:
    return TeamPerson(
        id=u.id,
        display_name=u.display_name,
        department_name=u.department.name if u.department else None,
        job_title=u.job_title,
    )


async def team_day(
    session: AsyncSession,
    user: CurrentUser,
    settings: Settings,
    day: date | None,
    department_id: uuid.UUID | None,
) -> TeamDay:
    scope = _scope(user, department_id)
    day = day or (await _now(session, settings)).date()
    people = (
        (await session.scalars(select(User).where(scope).order_by(User.display_name)))
        .unique()
        .all()
    )
    ids = [p.id for p in people]
    records = {
        r.user_id: r
        for r in (
            await session.scalars(
                select(AttendanceRecord).where(
                    AttendanceRecord.user_id.in_(ids), AttendanceRecord.work_date == day
                )
            )
        ).all()
    }
    leave = await _leave_on(session, ids, day)
    rows = [
        TeamDayRow(
            person=_person(p),
            record=_out(records[p.id]) if p.id in records else None,
            on_leave=leave.get(p.id),
        )
        for p in people
    ]
    return TeamDay(
        date=day,
        rows=rows,
        present=sum(1 for r in rows if r.record),
        late=sum(1 for r in rows if r.record and r.record.late),
        on_leave=sum(1 for r in rows if r.on_leave and not r.record),
        missing=sum(1 for r in rows if not r.record and not r.on_leave),
    )


async def monthly_report(
    session: AsyncSession,
    user: CurrentUser,
    settings: Settings,
    month: str | None,
    department_id: uuid.UUID | None,
) -> MonthlyReport:
    scope = _scope(user, department_id)
    now = await _now(session, settings)
    label, first, last = _month_range(month, now.date())
    people = (
        (await session.scalars(select(User).where(scope).order_by(User.display_name)))
        .unique()
        .all()
    )
    ids = [p.id for p in people]
    by_user: dict[uuid.UUID, list[AttendanceRecord]] = defaultdict(list)
    for r in (
        await session.scalars(
            select(AttendanceRecord).where(
                AttendanceRecord.user_id.in_(ids), AttendanceRecord.work_date.between(first, last)
            )
        )
    ).all():
        by_user[r.user_id].append(r)
    leave_days: dict[uuid.UUID, float] = defaultdict(float)
    for lr in (
        await session.scalars(
            select(LeaveRequest).where(
                LeaveRequest.user_id.in_(ids),
                LeaveRequest.status == LeaveStatus.APPROVED.value,
                LeaveRequest.start_date <= last,
                LeaveRequest.end_date >= first,
            )
        )
    ).all():
        start, end = max(lr.start_date, first), min(lr.end_date, last)
        leave_days[lr.user_id] += float(working_days(start, end, HalfDay(lr.half_day)))
    rows = []
    for p in people:
        s = _summary(by_user.get(p.id, []), settings)
        rows.append(
            MonthlyRow(
                person=_person(p),
                days_present=s.days_present,
                late_days=s.late_days,
                wfh_days=s.wfh_days,
                leave_days=leave_days.get(p.id, 0.0),
                total_minutes=s.total_minutes,
            )
        )
    return MonthlyReport(month=label, working_days=int(working_days(first, last)), rows=rows)


def report_csv(report: MonthlyReport) -> str:
    out = io.StringIO()
    out.write("﻿")  # BOM so Excel opens Thai text correctly
    writer = csv.writer(out)
    writer.writerow(
        ["ชื่อ", "แผนก", "วันที่มาทำงาน", "มาสาย (วัน)", "WFH (วัน)", "ลา (วัน)", "ชั่วโมงทำงานรวม"]
    )
    for r in report.rows:
        writer.writerow(
            [
                r.person.display_name,
                r.person.department_name or "",
                r.days_present,
                r.late_days,
                r.wfh_days,
                f"{r.leave_days:g}",
                f"{r.total_minutes / 60:.1f}",
            ]
        )
    return out.getvalue()
