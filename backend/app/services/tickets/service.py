"""IT helpdesk business rules.

| operation                         | allowed for                                                 |
| --------------------------------- | ----------------------------------------------------------- |
| create                            | ``tickets:create``                                          |
| see, public comment               | the requester (``tickets:read_own``) or ``tickets:read_all`` |
| internal note (hidden from users) | ``tickets:comment_internal``                                |
| any status change, category,      | ``tickets:manage``                                          |
| priority                          |                                                             |
| assign                            | ``tickets:assign`` (assignee holds ``tickets:manage``)      |
| requester: cancel an open ticket, | the requester                                               |
| close or reopen a resolved one    |                                                             |

A requester's reply to a ticket waiting for them moves it back to IN_PROGRESS.
Unknown and invisible tickets both answer 404.
"""

from __future__ import annotations

import uuid
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import NotFoundError, PermissionDeniedError, ValidationFailedError
from app.core.permissions import P
from app.core.principal import CurrentUser, RequestMeta
from app.core.security import utcnow
from app.models.notification import NotificationType
from app.models.ticket import (
    Ticket,
    TicketCategory,
    TicketComment,
    TicketEvent,
    TicketEventType,
    TicketStatus,
)
from app.repositories import tickets as ticket_repo
from app.repositories.documents import user_names
from app.repositories.tickets import TicketRow
from app.schemas.common import ErrorDetail
from app.schemas.documents import UserRef
from app.schemas.tickets import (
    TicketCapabilities,
    TicketCommentOut,
    TicketCreate,
    TicketDetail,
    TicketEventOut,
    TicketListItem,
    TicketUpdate,
)
from app.services import audit, notifications
from app.services.audit import AuditAction

NOT_FOUND = "ไม่พบรายการแจ้งปัญหา หรือคุณไม่มีสิทธิ์เข้าถึง"

STATUS_LABELS = {
    TicketStatus.OPEN: "รอรับเรื่อง",
    TicketStatus.IN_PROGRESS: "กำลังดำเนินการ",
    TicketStatus.WAITING_FOR_USER: "รอข้อมูลจากผู้แจ้ง",
    TicketStatus.RESOLVED: "แก้ไขแล้ว",
    TicketStatus.CLOSED: "ปิดเรื่อง",
    TicketStatus.CANCELLED: "ยกเลิก",
}
CATEGORY_LABELS = {
    TicketCategory.COMPUTER: "คอมพิวเตอร์",
    TicketCategory.NETWORK: "เครือข่าย/อินเทอร์เน็ต",
    TicketCategory.PRINTER: "เครื่องพิมพ์",
    TicketCategory.SOFTWARE: "โปรแกรม",
    TicketCategory.ACCOUNT_ACCESS: "บัญชีและสิทธิ์เข้าใช้",
    TicketCategory.OTHER: "อื่นๆ",
}


def allowed_statuses(user: CurrentUser, ticket: Ticket) -> list[TicketStatus]:
    current = TicketStatus(ticket.status)
    if user.has(P.TICKETS_MANAGE):
        return [s for s in TicketStatus if s is not current]
    if ticket.requester_id != user.id:
        return []
    if current.is_open:
        return [TicketStatus.CANCELLED]
    if current is TicketStatus.RESOLVED:
        return [TicketStatus.CLOSED, TicketStatus.OPEN]
    return []


def capabilities_for(user: CurrentUser, ticket: Ticket) -> TicketCapabilities:
    return TicketCapabilities(
        can_manage=user.has(P.TICKETS_MANAGE),
        can_assign=user.has(P.TICKETS_ASSIGN),
        can_comment=True,
        can_comment_internal=user.has(P.TICKETS_COMMENT_INTERNAL),
        allowed_statuses=allowed_statuses(user, ticket),
    )


def _deny(allowed: bool, message: str) -> None:
    if not allowed:
        raise PermissionDeniedError(message)


async def _visible(session: AsyncSession, user: CurrentUser, ticket_id: uuid.UUID) -> TicketRow:
    row = await ticket_repo.get_ticket(session, user, ticket_id)
    if row is None:
        raise NotFoundError(NOT_FOUND)
    return row


async def _lock(session: AsyncSession, ticket_id: uuid.UUID) -> Ticket:
    ticket = await ticket_repo.get_for_update(session, ticket_id)
    if ticket is None:
        raise NotFoundError(NOT_FOUND)
    return ticket


def _event(
    session: AsyncSession,
    ticket: Ticket,
    actor: CurrentUser,
    kind: TicketEventType,
    *,
    from_value: str | None = None,
    to_value: str | None = None,
    internal: bool = False,
) -> None:
    session.add(
        TicketEvent(
            ticket_id=ticket.id,
            actor_id=actor.id,
            event_type=kind.value,
            from_value=from_value,
            to_value=to_value,
            is_internal=internal,
        )
    )


def _link(ticket: Ticket) -> str:
    return f"/helpdesk/{ticket.id}"


def _notify(
    session: AsyncSession, user_id: uuid.UUID, ticket: Ticket, title: str, body: str
) -> None:
    notifications.notify(
        session,
        user_id=user_id,
        type=NotificationType.TICKET,
        title=f"{ticket.ticket_number} {title}",
        body=body,
        link_url=_link(ticket),
        entity_type="ticket",
        entity_id=ticket.id,
    )


# --- Commands -------------------------------------------------------------------------


async def create_ticket(
    session: AsyncSession,
    settings: Settings,
    user: CurrentUser,
    data: TicketCreate,
    meta: RequestMeta,
) -> uuid.UUID:
    _deny(user.has(P.TICKETS_CREATE), "คุณไม่มีสิทธิ์แจ้งปัญหาไอที")
    year = utcnow().astimezone(ZoneInfo(settings.app_timezone)).year
    number = await ticket_repo.next_number(session)
    ticket = Ticket(
        ticket_number=f"IT-{year}-{number:06d}",
        title=data.title,
        description=data.description,
        category=data.category.value,
        priority=data.priority.value,
        status=TicketStatus.OPEN.value,
        requester_id=user.id,
    )
    session.add(ticket)
    await session.flush()
    _event(session, ticket, user, TicketEventType.CREATED, to_value=ticket.ticket_number)
    # The people who dispatch tickets hear about new ones.
    for lead in await ticket_repo.users_with_permission(session, P.TICKETS_ASSIGN):
        if lead.id != user.id:
            _notify(
                session,
                lead.id,
                ticket,
                f"แจ้งปัญหาใหม่: {ticket.title}",
                f"{user.display_name} · {CATEGORY_LABELS[data.category]}",
            )
    audit.record(
        session,
        AuditAction.TICKET_CREATED,
        actor_id=user.id,
        meta=meta,
        entity_type="ticket",
        entity_id=ticket.id,
        details={"number": ticket.ticket_number, "category": ticket.category},
    )
    await session.commit()
    return ticket.id


async def change_status(
    session: AsyncSession,
    user: CurrentUser,
    ticket_id: uuid.UUID,
    status: TicketStatus,
    meta: RequestMeta,
) -> None:
    row = await _visible(session, user, ticket_id)
    _deny(
        status in allowed_statuses(user, row.ticket),
        "คุณเปลี่ยนสถานะรายการนี้เป็นสถานะที่เลือกไม่ได้",
    )
    ticket = await _lock(session, ticket_id)
    previous = TicketStatus(ticket.status)
    now = utcnow()
    ticket.status = status.value
    if status is TicketStatus.RESOLVED:
        ticket.resolved_at = now
    elif status is TicketStatus.CLOSED:
        ticket.closed_at = now
        ticket.resolved_at = ticket.resolved_at or now
    elif status.is_open:
        ticket.resolved_at = None
        ticket.closed_at = None
    _event(
        session,
        ticket,
        user,
        TicketEventType.STATUS_CHANGED,
        from_value=previous.value,
        to_value=status.value,
    )
    label = STATUS_LABELS[status]
    if ticket.requester_id != user.id:
        _notify(
            session,
            ticket.requester_id,
            ticket,
            f"สถานะ: {label}",
            f"{user.display_name} เปลี่ยนสถานะเป็น {label}",
        )
    elif ticket.assignee_id and ticket.assignee_id != user.id:
        _notify(session, ticket.assignee_id, ticket, f"ผู้แจ้งเปลี่ยนสถานะ: {label}", ticket.title)
    audit.record(
        session,
        AuditAction.TICKET_STATUS_CHANGED,
        actor_id=user.id,
        meta=meta,
        entity_type="ticket",
        entity_id=ticket.id,
        details={"from": previous.value, "to": status.value},
    )
    await session.commit()


async def assign(
    session: AsyncSession,
    user: CurrentUser,
    ticket_id: uuid.UUID,
    assignee_id: uuid.UUID | None,
    meta: RequestMeta,
) -> None:
    _deny(user.has(P.TICKETS_ASSIGN), "คุณไม่มีสิทธิ์มอบหมายรายการแจ้งปัญหา")
    await _visible(session, user, ticket_id)
    if assignee_id is not None and not await ticket_repo.has_permission(
        session, assignee_id, P.TICKETS_MANAGE
    ):
        raise ValidationFailedError(
            details=[ErrorDetail(field="assignee_id", message="มอบหมายได้เฉพาะเจ้าหน้าที่ไอที")]
        )
    ticket = await _lock(session, ticket_id)
    if ticket.assignee_id == assignee_id:
        await session.rollback()
        return
    names = await user_names(session, {i for i in (ticket.assignee_id, assignee_id) if i})
    previous = ticket.assignee_id
    ticket.assignee_id = assignee_id
    if assignee_id is None:
        _event(
            session,
            ticket,
            user,
            TicketEventType.UNASSIGNED,
            from_value=names.get(previous) if previous else None,
        )
    else:
        _event(session, ticket, user, TicketEventType.ASSIGNED, to_value=names.get(assignee_id))
        if ticket.status == TicketStatus.OPEN.value:
            ticket.status = TicketStatus.IN_PROGRESS.value
            _event(
                session,
                ticket,
                user,
                TicketEventType.STATUS_CHANGED,
                from_value=TicketStatus.OPEN.value,
                to_value=TicketStatus.IN_PROGRESS.value,
            )
        if assignee_id != user.id:
            _notify(
                session,
                assignee_id,
                ticket,
                f"มอบหมายให้คุณ: {ticket.title}",
                f"โดย {user.display_name}",
            )
    audit.record(
        session,
        AuditAction.TICKET_ASSIGNED,
        actor_id=user.id,
        meta=meta,
        entity_type="ticket",
        entity_id=ticket.id,
        details={"assignee": str(assignee_id) if assignee_id else None},
    )
    await session.commit()


async def update(
    session: AsyncSession,
    user: CurrentUser,
    ticket_id: uuid.UUID,
    data: TicketUpdate,
    meta: RequestMeta,
) -> None:
    _deny(user.has(P.TICKETS_MANAGE), "คุณไม่มีสิทธิ์แก้ไขรายการแจ้งปัญหา")
    await _visible(session, user, ticket_id)
    ticket = await _lock(session, ticket_id)
    changed: list[str] = []
    if data.category is not None and data.category.value != ticket.category:
        _event(
            session,
            ticket,
            user,
            TicketEventType.CATEGORY_CHANGED,
            from_value=ticket.category,
            to_value=data.category.value,
        )
        ticket.category = data.category.value
        changed.append("category")
    if data.priority is not None and data.priority.value != ticket.priority:
        _event(
            session,
            ticket,
            user,
            TicketEventType.PRIORITY_CHANGED,
            from_value=ticket.priority,
            to_value=data.priority.value,
        )
        ticket.priority = data.priority.value
        changed.append("priority")
    if not changed:
        await session.rollback()
        return
    audit.record(
        session,
        AuditAction.TICKET_UPDATED,
        actor_id=user.id,
        meta=meta,
        entity_type="ticket",
        entity_id=ticket.id,
        details={"fields": changed},
    )
    await session.commit()


async def add_comment(
    session: AsyncSession, user: CurrentUser, ticket_id: uuid.UUID, body: str, internal: bool
) -> None:
    await _visible(session, user, ticket_id)
    if internal:
        _deny(user.has(P.TICKETS_COMMENT_INTERNAL), "บันทึกภายในใช้ได้เฉพาะทีมไอที")
    ticket = await _lock(session, ticket_id)
    session.add(
        TicketComment(ticket_id=ticket.id, author_id=user.id, body=body, is_internal=internal)
    )
    _event(session, ticket, user, TicketEventType.COMMENTED, internal=internal)
    ticket.updated_at = utcnow()
    if internal:
        await session.commit()
        return
    excerpt = body if len(body) <= 140 else body[:139] + "…"
    if user.id == ticket.requester_id:
        if ticket.status == TicketStatus.WAITING_FOR_USER.value:
            ticket.status = TicketStatus.IN_PROGRESS.value
            _event(
                session,
                ticket,
                user,
                TicketEventType.STATUS_CHANGED,
                from_value=TicketStatus.WAITING_FOR_USER.value,
                to_value=TicketStatus.IN_PROGRESS.value,
            )
        recipients = (
            [ticket.assignee_id]
            if ticket.assignee_id
            else [u.id for u in await ticket_repo.users_with_permission(session, P.TICKETS_ASSIGN)]
        )
        for rid in recipients:
            if rid != user.id:
                _notify(session, rid, ticket, "ผู้แจ้งตอบกลับ", f"{user.display_name}: {excerpt}")
    else:
        _notify(
            session, ticket.requester_id, ticket, "ทีมไอทีตอบกลับ", f"{user.display_name}: {excerpt}"
        )
    await session.commit()


# --- Queries --------------------------------------------------------------------------


def _item(row: TicketRow) -> TicketListItem:
    t = row.ticket
    return TicketListItem(
        id=t.id,
        ticket_number=t.ticket_number,
        title=t.title,
        category=TicketCategory(t.category),
        priority=t.priority,
        status=TicketStatus(t.status),
        requester=UserRef(id=t.requester_id, display_name=row.requester_name),
        assignee=UserRef(id=t.assignee_id, display_name=row.assignee_name or "")
        if t.assignee_id
        else None,
        created_at=t.created_at,
        updated_at=t.updated_at,
        resolved_at=t.resolved_at,
        closed_at=t.closed_at,
    )


def list_item(row: TicketRow) -> TicketListItem:
    return _item(row)


async def detail(session: AsyncSession, user: CurrentUser, ticket_id: uuid.UUID) -> TicketDetail:
    row = await _visible(session, user, ticket_id)
    return TicketDetail(
        **_item(row).model_dump(),
        description=row.ticket.description,
        capabilities=capabilities_for(user, row.ticket),
    )


async def comments(
    session: AsyncSession, user: CurrentUser, ticket_id: uuid.UUID
) -> list[TicketCommentOut]:
    await _visible(session, user, ticket_id)
    internal = user.has(P.TICKETS_COMMENT_INTERNAL)
    return [
        TicketCommentOut(
            id=c.id,
            author=UserRef(id=c.author_id, display_name=name or "ผู้ใช้ที่ถูกลบ")
            if c.author_id
            else None,
            body=c.body,
            is_internal=c.is_internal,
            created_at=c.created_at,
        )
        for c, name in await ticket_repo.list_comments(
            session, ticket_id, include_internal=internal
        )
    ]


async def history(
    session: AsyncSession, user: CurrentUser, ticket_id: uuid.UUID
) -> list[TicketEventOut]:
    await _visible(session, user, ticket_id)
    internal = user.has(P.TICKETS_COMMENT_INTERNAL)
    return [
        TicketEventOut(
            id=e.id,
            event_type=e.event_type,
            actor=UserRef(id=e.actor_id, display_name=name or "ผู้ใช้ที่ถูกลบ") if e.actor_id else None,
            from_value=e.from_value,
            to_value=e.to_value,
            is_internal=e.is_internal,
            created_at=e.created_at,
        )
        for e, name in await ticket_repo.list_events(session, ticket_id, include_internal=internal)
    ]
