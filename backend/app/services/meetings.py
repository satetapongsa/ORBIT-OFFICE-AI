"""Calendar meetings (ADR-070).

* A meeting is visible to its organizer and attendees only; others get 404.
* The organizer edits, changes attendees and cancels; attendees answer
  (accepted / tentative / declined). Invitations, changes, cancellations and declines notify
  the people concerned; a reminder goes out ``reminder_minutes`` before the start (Celery beat).
* Availability: overlapping meetings and approved leave of the chosen people are reported
  before saving; titles of meetings the viewer is not part of are never shown.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from app.core.permissions import P
from app.core.principal import CurrentUser, RequestMeta
from app.models.identity import User
from app.models.leave import LeaveRequest, LeaveStatus, LeaveType
from app.models.meeting import Meeting, MeetingAttendee, MeetingResponse
from app.models.notification import NotificationType
from app.schemas.common import ErrorDetail
from app.schemas.meetings import (
    AttendeeOut,
    AvailabilityOut,
    CalendarFeed,
    Conflict,
    LeaveEvent,
    MeetingCreate,
    MeetingOut,
    MeetingPerson,
    MeetingRespond,
    MeetingUpdate,
)
from app.services import audit, notifications
from app.services.audit import AuditAction

NOT_FOUND = "ไม่พบการประชุมนี้"
LINK = "/calendar"
MAX_DURATION = timedelta(hours=24)
MONTHS = (
    "ม.ค.",
    "ก.พ.",
    "มี.ค.",
    "เม.ย.",
    "พ.ค.",
    "มิ.ย.",
    "ก.ค.",
    "ส.ค.",
    "ก.ย.",
    "ต.ค.",
    "พ.ย.",
    "ธ.ค.",
)
RESPONSE_TEXT = {"ACCEPTED": "ตอบรับ", "TENTATIVE": "อาจเข้าร่วม", "DECLINED": "ปฏิเสธ"}


def _fail(field: str, message: str) -> ValidationFailedError:
    return ValidationFailedError(details=[ErrorDetail(field=field, message=message)])


def when(start: datetime, end: datetime, tz: str) -> str:
    """ "23 พ.ย. 14:00-15:00" in the business time zone."""
    zone = ZoneInfo(tz)
    s, e = start.astimezone(zone), end.astimezone(zone)
    months = MONTHS
    day = f"{s.day} {months[s.month - 1]}"
    if s.date() == e.date():
        return f"{day} {s:%H:%M}-{e:%H:%M}"
    return f"{day} {s:%H:%M} - {e.day} {months[e.month - 1]} {e:%H:%M}"


def _check_times(start: datetime, end: datetime) -> None:
    if start.tzinfo is None or end.tzinfo is None:
        raise _fail("start_at", "ต้องระบุเขตเวลา")
    if end <= start:
        raise _fail("end_at", "เวลาสิ้นสุดต้องหลังเวลาเริ่ม")
    if end - start > MAX_DURATION:
        raise _fail("end_at", "การประชุมยาวได้ไม่เกิน 24 ชั่วโมง")


def _visible(user: CurrentUser) -> ColumnElement[bool]:
    attending = select(MeetingAttendee.meeting_id).where(MeetingAttendee.user_id == user.id)
    return or_(Meeting.organizer_id == user.id, Meeting.id.in_(attending))


async def _active_users(session: AsyncSession, ids: Iterable[uuid.UUID]) -> list[User]:
    wanted = set(ids)
    if not wanted:
        return []
    found = (
        (
            await session.scalars(
                select(User).where(
                    User.id.in_(wanted), User.is_active.is_(True), User.deleted_at.is_(None)
                )
            )
        )
        .unique()
        .all()
    )
    if len(found) != len(wanted):
        raise _fail("attendee_ids", "มีผู้เข้าร่วมที่ไม่พบหรือบัญชีถูกระงับ")
    return list(found)


def _person(u: User) -> MeetingPerson:
    return MeetingPerson(
        id=u.id,
        display_name=u.display_name,
        department_name=u.department.name if u.department else None,
    )


async def _outs(
    session: AsyncSession, user: CurrentUser, meetings: Sequence[Meeting]
) -> list[MeetingOut]:
    if not meetings:
        return []
    ids = [m.id for m in meetings]
    rows = (
        (
            await session.execute(
                select(MeetingAttendee, User)
                .join(User, User.id == MeetingAttendee.user_id)
                .where(MeetingAttendee.meeting_id.in_(ids))
                .order_by(User.display_name)
            )
        )
        .unique()
        .all()
    )
    by_meeting: dict[uuid.UUID, list[tuple[MeetingAttendee, User]]] = {}
    for attendee, person in rows:
        by_meeting.setdefault(attendee.meeting_id, []).append((attendee, person))
    organizers = {
        u.id: u
        for u in (
            await session.scalars(
                select(User).where(
                    User.id.in_({m.organizer_id for m in meetings if m.organizer_id})
                )
            )
        ).unique()
    }
    out = []
    for m in meetings:
        attendees = by_meeting.get(m.id, [])
        mine = next((a.response for a, p in attendees if p.id == user.id), None)
        organizer = organizers.get(m.organizer_id) if m.organizer_id else None
        out.append(
            MeetingOut(
                id=m.id,
                title=m.title,
                description=m.description,
                location=m.location,
                online_url=m.online_url,
                start_at=m.start_at,
                end_at=m.end_at,
                organizer=_person(organizer) if organizer else None,
                attendees=[
                    AttendeeOut(
                        **_person(p).model_dump(),
                        response=MeetingResponse(a.response),
                        is_organizer=p.id == m.organizer_id,
                    )
                    for a, p in sorted(attendees, key=lambda ap: ap[1].id != m.organizer_id)
                ],
                my_response=MeetingResponse(mine) if mine else None,
                is_organizer=m.organizer_id == user.id,
                cancelled=m.cancelled_at is not None,
                reminder_minutes=m.reminder_minutes,
            )
        )
    return out


def _notify(
    session: AsyncSession | Session,
    recipients: Iterable[uuid.UUID],
    meeting: Meeting,
    title: str,
    body: str,
) -> None:
    for recipient in set(recipients):
        notifications.notify(
            session,
            user_id=recipient,
            type=NotificationType.MEETING,
            title=title,
            body=body,
            link_url=f"{LINK}?meeting={meeting.id}",
            entity_type="meeting",
            entity_id=meeting.id,
        )


async def _get_visible(session: AsyncSession, user: CurrentUser, meeting_id: uuid.UUID) -> Meeting:
    meeting = await session.scalar(select(Meeting).where(Meeting.id == meeting_id, _visible(user)))
    if meeting is None:
        raise NotFoundError(NOT_FOUND)
    return meeting


async def _attendee_ids(session: AsyncSession, meeting_id: uuid.UUID) -> list[uuid.UUID]:
    return list(
        (
            await session.scalars(
                select(MeetingAttendee.user_id).where(MeetingAttendee.meeting_id == meeting_id)
            )
        ).all()
    )


# --- Queries ------------------------------------------------------------------------------


async def calendar(
    session: AsyncSession, user: CurrentUser, start: date, end: date, settings: Settings
) -> CalendarFeed:
    if end < start or (end - start).days > 62:
        raise _fail("end", "ช่วงวันที่ต้องไม่เกิน 62 วัน")
    zone = ZoneInfo(settings.app_timezone)
    lower = datetime.combine(start, datetime.min.time(), zone)
    upper = datetime.combine(end + timedelta(days=1), datetime.min.time(), zone)
    meetings = (
        await session.scalars(
            select(Meeting)
            .where(_visible(user), Meeting.start_at < upper, Meeting.end_at > lower)
            .order_by(Meeting.start_at)
            .limit(500)
        )
    ).all()
    leave: list[LeaveEvent] = []
    if user.has(P.LEAVE_REQUEST):
        stmt = (
            select(LeaveRequest, User.display_name, LeaveType.name, LeaveType.color)
            .join(User, User.id == LeaveRequest.user_id)
            .join(LeaveType, LeaveType.id == LeaveRequest.leave_type_id)
            .where(
                LeaveRequest.status == LeaveStatus.APPROVED.value,
                LeaveRequest.start_date <= end,
                LeaveRequest.end_date >= start,
                User.is_active.is_(True),
            )
        )
        if not user.has(P.LEAVE_MANAGE):
            mine: ColumnElement[bool] = LeaveRequest.user_id == user.id
            stmt = stmt.where(
                or_(mine, User.department_id == user.department_id) if user.department_id else mine
            )
        for lr, name, type_name, color in (await session.execute(stmt.limit(500))).all():
            leave.append(
                LeaveEvent(
                    id=lr.id,
                    person_name=name,
                    leave_type=type_name,
                    color=color,
                    start_date=lr.start_date,
                    end_date=lr.end_date,
                    half_day=lr.half_day,
                )
            )
    return CalendarFeed(meetings=await _outs(session, user, meetings), leave=leave)


async def get_meeting(
    session: AsyncSession, user: CurrentUser, meeting_id: uuid.UUID
) -> MeetingOut:
    return (await _outs(session, user, [await _get_visible(session, user, meeting_id)]))[0]


async def availability(
    session: AsyncSession,
    user: CurrentUser,
    start: datetime,
    end: datetime,
    user_ids: Sequence[uuid.UUID],
    exclude_meeting_id: uuid.UUID | None,
    settings: Settings,
) -> AvailabilityOut:
    _check_times(start, end)
    if not user_ids:
        return AvailabilityOut(conflicts=[])
    names = dict(
        (
            await session.execute(select(User.id, User.display_name).where(User.id.in_(user_ids)))
        ).all()
    )
    conflicts: list[Conflict] = []
    stmt = (
        select(MeetingAttendee.user_id, Meeting)
        .join(Meeting, Meeting.id == MeetingAttendee.meeting_id)
        .where(
            MeetingAttendee.user_id.in_(user_ids),
            MeetingAttendee.response != MeetingResponse.DECLINED.value,
            Meeting.cancelled_at.is_(None),
            Meeting.start_at < end,
            Meeting.end_at > start,
        )
    )
    if exclude_meeting_id is not None:
        stmt = stmt.where(Meeting.id != exclude_meeting_id)
    mine = set(
        (
            await session.scalars(
                select(MeetingAttendee.meeting_id).where(MeetingAttendee.user_id == user.id)
            )
        ).all()
    )
    for uid, meeting in (await session.execute(stmt)).all():
        label = f"“{meeting.title}”" if meeting.id in mine else "ประชุมอื่น"
        conflicts.append(
            Conflict(
                user_id=uid,
                display_name=names.get(uid, ""),
                kind="meeting",
                detail=f"ติด{label} {when(meeting.start_at, meeting.end_at, settings.app_timezone)}",
            )
        )
    zone = ZoneInfo(settings.app_timezone)
    first, last = start.astimezone(zone).date(), end.astimezone(zone).date()
    for uid, type_name in (
        await session.execute(
            select(LeaveRequest.user_id, LeaveType.name)
            .join(LeaveType, LeaveType.id == LeaveRequest.leave_type_id)
            .where(
                LeaveRequest.user_id.in_(user_ids),
                LeaveRequest.status == LeaveStatus.APPROVED.value,
                LeaveRequest.start_date <= last,
                LeaveRequest.end_date >= first,
            )
        )
    ).all():
        conflicts.append(
            Conflict(
                user_id=uid,
                display_name=names.get(uid, ""),
                kind="leave",
                detail=f"{type_name}ในวันนั้น",
            )
        )
    return AvailabilityOut(conflicts=conflicts)


# --- Changes ------------------------------------------------------------------------------


async def create_meeting(
    session: AsyncSession,
    user: CurrentUser,
    data: MeetingCreate,
    meta: RequestMeta,
    settings: Settings,
) -> MeetingOut:
    _check_times(data.start_at, data.end_at)
    now = await session.scalar(select(func.now()))
    if now is not None and data.end_at <= now:
        raise _fail("end_at", "ไม่สามารถนัดประชุมในเวลาที่ผ่านไปแล้ว")
    invitees = await _active_users(session, [i for i in data.attendee_ids if i != user.id])
    meeting = Meeting(
        title=data.title,
        description=data.description,
        location=data.location or None,
        online_url=data.online_url,
        start_at=data.start_at,
        end_at=data.end_at,
        organizer_id=user.id,
        reminder_minutes=data.reminder_minutes,
    )
    session.add(meeting)
    await session.flush()
    session.add(
        MeetingAttendee(
            meeting_id=meeting.id, user_id=user.id, response=MeetingResponse.ACCEPTED.value
        )
    )
    for invitee in invitees:
        session.add(MeetingAttendee(meeting_id=meeting.id, user_id=invitee.id))
    _notify(
        session,
        [i.id for i in invitees],
        meeting,
        f"{user.display_name} เชิญคุณประชุม: {data.title}",
        when(data.start_at, data.end_at, settings.app_timezone)
        + (f" · {data.location}" if data.location else "")
        + (" · ออนไลน์" if data.online_url else ""),
    )
    audit.record(
        session,
        AuditAction.MEETING_CREATED,
        actor_id=user.id,
        meta=meta,
        entity_type="meeting",
        entity_id=meeting.id,
        details={"attendees": len(invitees)},
    )
    await session.commit()
    return await get_meeting(session, user, meeting.id)


async def update_meeting(
    session: AsyncSession,
    user: CurrentUser,
    meeting_id: uuid.UUID,
    data: MeetingUpdate,
    meta: RequestMeta,
    settings: Settings,
) -> MeetingOut:
    meeting = await _get_visible(session, user, meeting_id)
    if meeting.organizer_id != user.id:
        raise PermissionDeniedError("แก้ไขได้เฉพาะผู้จัดการประชุม")
    if meeting.cancelled_at is not None:
        raise ConflictError("การประชุมนี้ถูกยกเลิกแล้ว")
    changes = data.model_dump(exclude_unset=True, exclude={"attendee_ids"})
    start = changes.get("start_at") or meeting.start_at
    end = changes.get("end_at") or meeting.end_at
    _check_times(start, end)
    time_changed = start != meeting.start_at or end != meeting.end_at
    for field, value in changes.items():
        if value is None and field not in {"location", "online_url"}:
            continue
        setattr(meeting, field, value)
    if time_changed:
        meeting.reminder_sent_at = None

    current = set(await _attendee_ids(session, meeting.id))
    added: set[uuid.UUID] = set()
    removed: set[uuid.UUID] = set()
    if data.attendee_ids is not None:
        wanted = {i for i in data.attendee_ids if i != user.id} | {user.id}
        await _active_users(session, wanted - current)
        added, removed = wanted - current, current - wanted - {user.id}
        if removed:
            await session.execute(
                delete(MeetingAttendee).where(
                    MeetingAttendee.meeting_id == meeting.id, MeetingAttendee.user_id.in_(removed)
                )
            )
        for uid in added:
            session.add(MeetingAttendee(meeting_id=meeting.id, user_id=uid))
    if time_changed:  # everyone answers again for the new time
        await session.execute(
            update(MeetingAttendee)
            .where(MeetingAttendee.meeting_id == meeting.id, MeetingAttendee.user_id != user.id)
            .values(response=MeetingResponse.PENDING.value, responded_at=None)
        )
    timing = when(start, end, settings.app_timezone)
    stay = current - removed - {user.id}
    if stay and (time_changed or changes):
        _notify(
            session,
            stay,
            meeting,
            f"อัปเดตการประชุม: {meeting.title}",
            ("เปลี่ยนเวลาเป็น " if time_changed else "") + timing,
        )
    _notify(session, added, meeting, f"{user.display_name} เชิญคุณประชุม: {meeting.title}", timing)
    _notify(session, removed, meeting, f"คุณถูกนำออกจากการประชุม: {meeting.title}", timing)
    audit.record(
        session,
        AuditAction.MEETING_UPDATED,
        actor_id=user.id,
        meta=meta,
        entity_type="meeting",
        entity_id=meeting.id,
        details={"fields": sorted(changes), "added": len(added), "removed": len(removed)},
    )
    await session.commit()
    return await get_meeting(session, user, meeting.id)


async def cancel_meeting(
    session: AsyncSession,
    user: CurrentUser,
    meeting_id: uuid.UUID,
    meta: RequestMeta,
    settings: Settings,
) -> MeetingOut:
    meeting = await _get_visible(session, user, meeting_id)
    if meeting.organizer_id != user.id:
        raise PermissionDeniedError("ยกเลิกได้เฉพาะผู้จัดการประชุม")
    if meeting.cancelled_at is not None:
        raise ConflictError("การประชุมนี้ถูกยกเลิกแล้ว")
    meeting.cancelled_at = func.now()
    others = [u for u in await _attendee_ids(session, meeting.id) if u != user.id]
    _notify(
        session,
        others,
        meeting,
        f"ยกเลิกการประชุม: {meeting.title}",
        when(meeting.start_at, meeting.end_at, settings.app_timezone)
        + f" — โดย {user.display_name}",
    )
    audit.record(
        session,
        AuditAction.MEETING_CANCELLED,
        actor_id=user.id,
        meta=meta,
        entity_type="meeting",
        entity_id=meeting.id,
    )
    await session.commit()
    return await get_meeting(session, user, meeting.id)


async def respond(
    session: AsyncSession, user: CurrentUser, meeting_id: uuid.UUID, data: MeetingRespond
) -> MeetingOut:
    meeting = await _get_visible(session, user, meeting_id)
    attendee = await session.get(MeetingAttendee, (meeting.id, user.id))
    if attendee is None:
        raise NotFoundError(NOT_FOUND)
    if meeting.cancelled_at is not None:
        raise ConflictError("การประชุมนี้ถูกยกเลิกแล้ว")
    if meeting.organizer_id == user.id:
        raise ConflictError("ผู้จัดการประชุมไม่ต้องตอบรับ")
    changed = attendee.response != data.response
    attendee.response = data.response
    attendee.responded_at = func.now()
    if changed and data.response == "DECLINED" and meeting.organizer_id:
        _notify(
            session,
            [meeting.organizer_id],
            meeting,
            f"{user.display_name} ปฏิเสธการประชุม: {meeting.title}",
            "",
        )
    await session.commit()
    return await get_meeting(session, user, meeting.id)


# --- Reminders (Celery beat, sync session) -------------------------------------------------


def send_due_reminders(session: Session, timezone: str) -> int:
    """Notifies attendees (not declined) of meetings starting within their reminder window."""
    now = session.scalar(select(func.now()))
    due = session.scalars(
        select(Meeting)
        .where(
            Meeting.cancelled_at.is_(None),
            Meeting.reminder_sent_at.is_(None),
            Meeting.reminder_minutes > 0,
            Meeting.start_at > now,
            Meeting.start_at - func.make_interval(0, 0, 0, 0, 0, Meeting.reminder_minutes) <= now,
        )
        .with_for_update(skip_locked=True)
    ).all()
    for meeting in due:
        recipients = session.scalars(
            select(MeetingAttendee.user_id).where(
                MeetingAttendee.meeting_id == meeting.id,
                MeetingAttendee.response != MeetingResponse.DECLINED.value,
            )
        ).all()
        _notify(
            session,
            recipients,
            meeting,
            f"อีก {meeting.reminder_minutes} นาที: {meeting.title}",
            when(meeting.start_at, meeting.end_at, timezone)
            + (f" · {meeting.location}" if meeting.location else ""),
        )
        meeting.reminder_sent_at = now
    return len(due)
