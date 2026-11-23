"""Leave requests (ADR-068).

* Days are working days (Monday-Friday); a single-day request can be a half day.
* Yearly quota per type (``leave_types.days_per_year``, overridable per person in
  ``leave_quotas``); pending requests reserve days, so the balance can never go negative.
* Approvers: holders of ``leave:approve_department`` in the requester's department, or holders
  of ``leave:manage`` (HR) for anyone. Nobody decides their own request.
* The requester may cancel a pending request, or an approved one that has not started;
  ``leave:manage`` may cancel any pending/approved request.
* Reasons are visible to the requester and approvers only (sick leave can be private).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from app.core.permissions import P
from app.core.principal import CurrentUser, RequestMeta
from app.models.identity import Permission, User, UserRole, role_permissions
from app.models.leave import (
    DEFAULT_LEAVE_TYPES,
    HalfDay,
    LeaveQuota,
    LeaveRequest,
    LeaveStatus,
    LeaveType,
)
from app.models.notification import NotificationType
from app.schemas.common import ErrorDetail
from app.schemas.leave import (
    LeaveBalance as LeaveBalance,
)
from app.schemas.leave import (
    LeaveDecision,
    LeavePerson,
    LeaveRequestCreate,
    LeaveRequestOut,
    LeaveScope,
    LeaveTypeOut,
    LeaveTypeUpdate,
    MyLeave,
    QuotaUpdate,
)
from app.services import audit, notifications
from app.services.audit import AuditAction

NOT_FOUND = "ไม่พบใบลานี้"
LINK = "/leave"
HALF = Decimal("0.5")
ACTIVE_STATUSES = (LeaveStatus.PENDING.value, LeaveStatus.APPROVED.value)
HALF_LABEL = {HalfDay.MORNING: " (ครึ่งเช้า)", HalfDay.AFTERNOON: " (ครึ่งบ่าย)", HalfDay.NONE: ""}


def _fail(field: str, message: str) -> ValidationFailedError:
    return ValidationFailedError(details=[ErrorDetail(field=field, message=message)])


def working_days(start: date, end: date, half_day: HalfDay = HalfDay.NONE) -> Decimal:
    """Monday-Friday between the dates (inclusive); a half day counts 0.5."""
    if end < start:
        return Decimal(0)
    if half_day is not HalfDay.NONE:
        return HALF if start.weekday() < 5 else Decimal(0)
    total = (end - start).days + 1
    weeks, rest = divmod(total, 7)
    days = weeks * 5 + sum(1 for i in range(rest) if (start + timedelta(days=i)).weekday() < 5)
    return Decimal(days)


def fmt_days(days: Decimal) -> str:
    """2 -> "2", 2.0 -> "2", 0.5 -> "0.5" (for messages)."""
    text = f"{Decimal(days):f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def today(settings: Settings) -> date:
    return datetime.now(ZoneInfo(settings.app_timezone)).date()


def _type_out(t: LeaveType) -> LeaveTypeOut:
    return LeaveTypeOut(
        id=t.id,
        code=t.code,
        name=t.name,
        days_per_year=t.days_per_year,
        color=t.color,
        is_active=t.is_active,
    )


async def ensure_types(session: AsyncSession) -> None:
    """Creates the default types on an empty table (fresh or reset database)."""
    if await session.scalar(select(func.count()).select_from(LeaveType)):
        return
    await session.execute(
        insert(LeaveType)
        .values(
            [
                {
                    "code": code,
                    "name": name,
                    "days_per_year": days,
                    "color": color,
                    "is_active": True,
                    "sort_order": i,
                }
                for i, (code, name, days, color) in enumerate(DEFAULT_LEAVE_TYPES, start=1)
            ]
        )
        .on_conflict_do_nothing(index_elements=["code"])
    )
    await session.commit()


async def list_types(session: AsyncSession, *, include_inactive: bool) -> list[LeaveTypeOut]:
    await ensure_types(session)
    stmt = select(LeaveType).order_by(LeaveType.sort_order, LeaveType.name)
    if not include_inactive:
        stmt = stmt.where(LeaveType.is_active.is_(True))
    return [_type_out(t) for t in (await session.scalars(stmt)).all()]


async def update_type(
    session: AsyncSession,
    user: CurrentUser,
    type_id: uuid.UUID,
    data: LeaveTypeUpdate,
    meta: RequestMeta,
) -> LeaveTypeOut:
    item = await session.get(LeaveType, type_id)
    if item is None:
        raise NotFoundError("ไม่พบประเภทการลานี้")
    if data.name is not None:
        item.name = data.name
    if data.unlimited:
        item.days_per_year = None
    elif data.days_per_year is not None:
        item.days_per_year = data.days_per_year
    if data.is_active is not None:
        item.is_active = data.is_active
    audit.record(
        session,
        AuditAction.LEAVE_SETTINGS_CHANGED,
        actor_id=user.id,
        meta=meta,
        entity_type="leave_type",
        entity_id=item.id,
        details=data.model_dump(mode="json", exclude_unset=True),
    )
    await session.commit()
    await session.refresh(item)
    return _type_out(item)


async def set_quota(
    session: AsyncSession, user: CurrentUser, data: QuotaUpdate, meta: RequestMeta
) -> None:
    if await session.get(LeaveType, data.leave_type_id) is None:
        raise _fail("leave_type_id", "ไม่พบประเภทการลานี้")
    if await session.get(User, data.user_id) is None:
        raise _fail("user_id", "ไม่พบพนักงานคนนี้")
    existing = await session.get(LeaveQuota, (data.user_id, data.leave_type_id, data.year))
    if data.days is None:
        if existing is not None:
            await session.delete(existing)
    elif existing is None:
        session.add(
            LeaveQuota(
                user_id=data.user_id,
                leave_type_id=data.leave_type_id,
                year=data.year,
                days=data.days,
            )
        )
    else:
        existing.days = data.days
    audit.record(
        session,
        AuditAction.LEAVE_SETTINGS_CHANGED,
        actor_id=user.id,
        meta=meta,
        entity_type="user",
        entity_id=data.user_id,
        details=data.model_dump(mode="json"),
    )
    await session.commit()


async def balances(session: AsyncSession, user_id: uuid.UUID, year: int) -> list[LeaveBalance]:
    await ensure_types(session)
    types = (
        await session.scalars(
            select(LeaveType)
            .where(LeaveType.is_active.is_(True))
            .order_by(LeaveType.sort_order, LeaveType.name)
        )
    ).all()
    overrides = {
        q.leave_type_id: q.days
        for q in (
            await session.scalars(
                select(LeaveQuota).where(LeaveQuota.user_id == user_id, LeaveQuota.year == year)
            )
        ).all()
    }
    sums = (
        await session.execute(
            select(LeaveRequest.leave_type_id, LeaveRequest.status, func.sum(LeaveRequest.days))
            .where(
                LeaveRequest.user_id == user_id,
                func.extract("year", LeaveRequest.start_date) == year,
                LeaveRequest.status.in_(ACTIVE_STATUSES),
            )
            .group_by(LeaveRequest.leave_type_id, LeaveRequest.status)
        )
    ).all()
    used: dict[uuid.UUID, Decimal] = {}
    pending: dict[uuid.UUID, Decimal] = {}
    for type_id, status, total in sums:
        target = used if status == LeaveStatus.APPROVED.value else pending
        target[type_id] = Decimal(total or 0)
    out = []
    for t in types:
        quota = overrides.get(t.id, t.days_per_year)
        u, p = used.get(t.id, Decimal(0)), pending.get(t.id, Decimal(0))
        out.append(
            LeaveBalance(
                leave_type=_type_out(t),
                year=year,
                quota=quota,
                used=u,
                pending=p,
                remaining=None if quota is None else quota - u - p,
            )
        )
    return out


# --- Who may see and decide ---------------------------------------------------------------


async def _users_with_permission(
    session: AsyncSession, code: str, *, department_id: uuid.UUID | None = None
) -> list[uuid.UUID]:
    stmt = (
        select(User.id)
        .join(UserRole, UserRole.user_id == User.id)
        .join(role_permissions, role_permissions.c.role_id == UserRole.role_id)
        .join(Permission, Permission.id == role_permissions.c.permission_id)
        .where(Permission.code == code, User.is_active.is_(True), User.deleted_at.is_(None))
        .distinct()
    )
    if department_id is not None:
        stmt = stmt.where(User.department_id == department_id)
    return list((await session.scalars(stmt)).all())


def _may_decide(user: CurrentUser, requester: User) -> bool:
    if requester.id == user.id:
        return False
    if user.has(P.LEAVE_MANAGE):
        return True
    return (
        user.has(P.LEAVE_APPROVE_DEPARTMENT)
        and user.department_id is not None
        and requester.department_id == user.department_id
    )


def _visible_to(user: CurrentUser) -> ColumnElement[bool]:
    """Requests the user may open in full (own, or ones they may decide)."""
    if user.has(P.LEAVE_MANAGE):
        return LeaveRequest.id.is_not(None)
    mine: ColumnElement[bool] = LeaveRequest.user_id == user.id
    if user.has(P.LEAVE_APPROVE_DEPARTMENT) and user.department_id is not None:
        return or_(mine, User.department_id == user.department_id)
    return mine


async def _outs(
    session: AsyncSession,
    user: CurrentUser,
    rows: Sequence[LeaveRequest],
    settings: Settings,
    *,
    hide_reasons: bool = False,
) -> list[LeaveRequestOut]:
    if not rows:
        return []
    people = {
        u.id: u
        for u in (
            await session.scalars(
                select(User).where(
                    User.id.in_(
                        {r.user_id for r in rows} | {r.decided_by for r in rows if r.decided_by}
                    )
                )
            )
        ).unique()
    }
    types = {
        t.id: t
        for t in (
            await session.scalars(
                select(LeaveType).where(LeaveType.id.in_({r.leave_type_id for r in rows}))
            )
        ).all()
    }
    now = today(settings)
    out = []
    for r in rows:
        person = people[r.user_id]
        own = r.user_id == user.id
        decider = _may_decide(user, person)
        status = LeaveStatus(r.status)
        can_cancel = (
            own
            and (
                status is LeaveStatus.PENDING
                or (status is LeaveStatus.APPROVED and r.start_date > now)
            )
        ) or (user.has(P.LEAVE_MANAGE) and status in (LeaveStatus.PENDING, LeaveStatus.APPROVED))
        out.append(
            LeaveRequestOut(
                id=r.id,
                person=LeavePerson(
                    id=person.id,
                    display_name=person.display_name,
                    department_name=person.department.name if person.department else None,
                ),
                leave_type=_type_out(types[r.leave_type_id]),
                start_date=r.start_date,
                end_date=r.end_date,
                half_day=HalfDay(r.half_day),
                days=r.days,
                reason=r.reason if (own or decider or not hide_reasons) else "",
                status=status,
                decided_by_name=people[r.decided_by].display_name
                if r.decided_by and r.decided_by in people
                else None,
                decided_at=r.decided_at,
                decision_note=r.decision_note if (own or decider) else None,
                created_at=r.created_at,
                can_decide=decider and status is LeaveStatus.PENDING,
                can_cancel=can_cancel,
            )
        )
    return out


# --- Requests -----------------------------------------------------------------------------


async def my_leave(
    session: AsyncSession, user: CurrentUser, settings: Settings, year: int | None
) -> MyLeave:
    year = year or today(settings).year
    rows = (
        await session.scalars(
            select(LeaveRequest)
            .where(
                LeaveRequest.user_id == user.id,
                func.extract("year", LeaveRequest.start_date) == year,
            )
            .order_by(LeaveRequest.start_date.desc(), LeaveRequest.created_at.desc())
        )
    ).all()
    return MyLeave(
        year=year,
        balances=await balances(session, user.id, year),
        requests=await _outs(session, user, rows, settings),
    )


async def create_request(
    session: AsyncSession,
    user: CurrentUser,
    settings: Settings,
    data: LeaveRequestCreate,
    meta: RequestMeta,
) -> LeaveRequestOut:
    await ensure_types(session)
    leave_type = await session.get(LeaveType, data.leave_type_id)
    if leave_type is None or not leave_type.is_active:
        raise _fail("leave_type_id", "ไม่พบประเภทการลานี้")
    if data.end_date < data.start_date:
        raise _fail("end_date", "วันสิ้นสุดต้องไม่ก่อนวันเริ่มลา")
    if data.start_date.year != data.end_date.year:
        raise _fail("end_date", "ใบลาข้ามปี กรุณายื่นแยกเป็นปีละใบ")
    if data.half_day is not HalfDay.NONE and data.start_date != data.end_date:
        raise _fail("half_day", "ลาครึ่งวันได้เฉพาะการลาวันเดียว")
    if (data.end_date - data.start_date).days > 366:
        raise _fail("end_date", "ช่วงวันลายาวเกินไป")
    days = working_days(data.start_date, data.end_date, data.half_day)
    if days <= 0:
        raise _fail("start_date", "ช่วงที่เลือกไม่มีวันทำงาน (จันทร์-ศุกร์)")

    overlapping = (
        await session.scalars(
            select(LeaveRequest).where(
                LeaveRequest.user_id == user.id,
                LeaveRequest.status.in_(ACTIVE_STATUSES),
                LeaveRequest.start_date <= data.end_date,
                LeaveRequest.end_date >= data.start_date,
            )
        )
    ).all()
    for other in overlapping:
        both_halves = (
            data.half_day is not HalfDay.NONE
            and other.half_day != HalfDay.NONE.value
            and other.half_day != data.half_day.value
        )
        if not both_halves:
            raise ConflictError(
                f"ช่วงวันนี้ซ้อนกับใบลาเดิม ({other.start_date:%d/%m/%Y} - {other.end_date:%d/%m/%Y})"
            )

    balance = next(
        (
            b
            for b in await balances(session, user.id, data.start_date.year)
            if b.leave_type.id == leave_type.id
        ),
        None,
    )
    if balance is not None and balance.remaining is not None and days > balance.remaining:
        raise _fail(
            "leave_type_id",
            f"{leave_type.name}คงเหลือ {fmt_days(balance.remaining)} วัน แต่ขอลา {fmt_days(days)} วัน",
        )

    item = LeaveRequest(
        user_id=user.id,
        leave_type_id=leave_type.id,
        start_date=data.start_date,
        end_date=data.end_date,
        half_day=data.half_day.value,
        days=days,
        reason=data.reason,
        status=LeaveStatus.PENDING.value,
    )
    session.add(item)
    await session.flush()

    approvers: list[uuid.UUID] = []
    if user.department_id is not None:
        approvers = await _users_with_permission(
            session, P.LEAVE_APPROVE_DEPARTMENT.value, department_id=user.department_id
        )
    approvers = [a for a in approvers if a != user.id] or [
        a for a in await _users_with_permission(session, P.LEAVE_MANAGE.value) if a != user.id
    ]
    period = (
        f"{data.start_date:%d/%m/%Y}"
        if data.start_date == data.end_date
        else f"{data.start_date:%d/%m/%Y} - {data.end_date:%d/%m/%Y}"
    )
    for approver in approvers:
        notifications.notify(
            session,
            user_id=approver,
            type=NotificationType.LEAVE,
            title=f"{user.display_name} ขอ{leave_type.name} {fmt_days(days)} วัน",
            body=f"{period}{HALF_LABEL[data.half_day]} — รอการอนุมัติ",
            link_url=f"{LINK}?tab=approvals",
            entity_type="leave_request",
            entity_id=item.id,
        )
    audit.record(
        session,
        AuditAction.LEAVE_REQUESTED,
        actor_id=user.id,
        meta=meta,
        entity_type="leave_request",
        entity_id=item.id,
        details={"type": leave_type.code, "days": str(days)},
    )
    await session.commit()
    await session.refresh(item)
    return (await _outs(session, user, [item], settings))[0]


async def _get_for_update(
    session: AsyncSession, request_id: uuid.UUID
) -> tuple[LeaveRequest, User]:
    item = await session.scalar(
        select(LeaveRequest).where(LeaveRequest.id == request_id).with_for_update()
    )
    if item is None:
        raise NotFoundError(NOT_FOUND)
    requester = await session.get(User, item.user_id)
    if requester is None:  # pragma: no cover - cascades with the user
        raise NotFoundError(NOT_FOUND)
    return item, requester


async def decide(
    session: AsyncSession,
    user: CurrentUser,
    settings: Settings,
    request_id: uuid.UUID,
    data: LeaveDecision,
    meta: RequestMeta,
) -> LeaveRequestOut:
    item, requester = await _get_for_update(session, request_id)
    if not _may_decide(user, requester):
        if item.user_id == user.id:
            raise PermissionDeniedError("อนุมัติใบลาของตนเองไม่ได้")
        raise NotFoundError(NOT_FOUND)
    if item.status != LeaveStatus.PENDING.value:
        raise ConflictError("ใบลานี้ได้รับการพิจารณาไปแล้ว")
    if not data.approve and not data.note:
        raise _fail("note", "กรุณาระบุเหตุผลที่ไม่อนุมัติ")
    leave_type = await session.get(LeaveType, item.leave_type_id)
    item.status = (LeaveStatus.APPROVED if data.approve else LeaveStatus.REJECTED).value
    item.decided_by = user.id
    item.decided_at = func.now()
    item.decision_note = data.note or None
    name = leave_type.name if leave_type else "การลา"
    notifications.notify(
        session,
        user_id=item.user_id,
        type=NotificationType.LEAVE,
        title=f"{name} {fmt_days(item.days)} วัน "
        + ("ได้รับอนุมัติแล้ว" if data.approve else "ไม่ได้รับอนุมัติ"),
        body=f"โดย {user.display_name}" + (f" — {data.note}" if data.note else ""),
        link_url=LINK,
        entity_type="leave_request",
        entity_id=item.id,
    )
    audit.record(
        session,
        AuditAction.LEAVE_APPROVED if data.approve else AuditAction.LEAVE_REJECTED,
        actor_id=user.id,
        meta=meta,
        entity_type="leave_request",
        entity_id=item.id,
    )
    await session.commit()
    await session.refresh(item)
    return (await _outs(session, user, [item], settings))[0]


async def cancel(
    session: AsyncSession,
    user: CurrentUser,
    settings: Settings,
    request_id: uuid.UUID,
    meta: RequestMeta,
) -> LeaveRequestOut:
    item, _requester = await _get_for_update(session, request_id)
    own = item.user_id == user.id
    if not own and not user.has(P.LEAVE_MANAGE):
        raise NotFoundError(NOT_FOUND)
    status = LeaveStatus(item.status)
    if status not in (LeaveStatus.PENDING, LeaveStatus.APPROVED):
        raise ConflictError("ใบลานี้ยกเลิกไม่ได้แล้ว")
    if (
        own
        and not user.has(P.LEAVE_MANAGE)
        and status is LeaveStatus.APPROVED
        and item.start_date <= today(settings)
    ):
        raise ConflictError("ใบลาที่อนุมัติแล้วและเริ่มลาแล้ว ยกเลิกเองไม่ได้ กรุณาติดต่อฝ่ายบุคคล")
    item.status = LeaveStatus.CANCELLED.value
    if not own:
        notifications.notify(
            session,
            user_id=item.user_id,
            type=NotificationType.LEAVE,
            title="ใบลาของคุณถูกยกเลิก",
            body=f"{item.start_date:%d/%m/%Y} - {item.end_date:%d/%m/%Y} โดย {user.display_name}",
            link_url=LINK,
            entity_type="leave_request",
            entity_id=item.id,
        )
    audit.record(
        session,
        AuditAction.LEAVE_CANCELLED,
        actor_id=user.id,
        meta=meta,
        entity_type="leave_request",
        entity_id=item.id,
    )
    await session.commit()
    await session.refresh(item)
    return (await _outs(session, user, [item], settings))[0]


async def list_requests(
    session: AsyncSession,
    user: CurrentUser,
    settings: Settings,
    *,
    scope: LeaveScope,
    status: LeaveStatus | None,
    limit: int,
) -> list[LeaveRequestOut]:
    if scope == "all" and not user.has(P.LEAVE_MANAGE):
        raise PermissionDeniedError("ต้องมีสิทธิ์จัดการการลาของทั้งองค์กร")
    if scope == "department" and not (
        user.has(P.LEAVE_APPROVE_DEPARTMENT) or user.has(P.LEAVE_MANAGE)
    ):
        raise PermissionDeniedError("ต้องมีสิทธิ์อนุมัติการลาของแผนก")
    stmt = (
        select(LeaveRequest)
        .join(User, User.id == LeaveRequest.user_id)
        .where(_visible_to(user), LeaveRequest.user_id != user.id)
    )
    if scope == "department" and user.department_id is not None:
        stmt = stmt.where(User.department_id == user.department_id)
    if scope == "approvals":
        stmt = stmt.where(LeaveRequest.status == LeaveStatus.PENDING.value)
    elif status is not None:
        stmt = stmt.where(LeaveRequest.status == status.value)
    rows = (
        await session.scalars(
            stmt.order_by(LeaveRequest.start_date.desc(), LeaveRequest.created_at.desc()).limit(
                limit
            )
        )
    ).all()
    outs = await _outs(session, user, rows, settings)
    if scope == "approvals":
        outs = [o for o in outs if o.can_decide]
    return outs


async def team_calendar(
    session: AsyncSession,
    user: CurrentUser,
    settings: Settings,
    start: date,
    end: date,
) -> list[LeaveRequestOut]:
    """Approved leave overlapping the period: my department (everyone in it may see who is
    away, without reasons) and myself; HR sees everyone."""
    if end < start or (end - start).days > 400:
        raise _fail("end", "ช่วงวันที่ไม่ถูกต้อง")
    stmt = (
        select(LeaveRequest)
        .join(User, User.id == LeaveRequest.user_id)
        .where(
            LeaveRequest.status == LeaveStatus.APPROVED.value,
            LeaveRequest.start_date <= end,
            LeaveRequest.end_date >= start,
            User.is_active.is_(True),
        )
    )
    if not user.has(P.LEAVE_MANAGE):
        own_department = (
            User.department_id == user.department_id if user.department_id is not None else None
        )
        stmt = stmt.where(
            or_(LeaveRequest.user_id == user.id, own_department)
            if own_department is not None
            else LeaveRequest.user_id == user.id
        )
    rows = (await session.scalars(stmt.order_by(LeaveRequest.start_date).limit(500))).all()
    return await _outs(session, user, rows, settings, hide_reasons=True)
