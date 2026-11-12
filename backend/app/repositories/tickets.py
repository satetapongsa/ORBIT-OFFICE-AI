"""Ticket queries. Visibility lives in :func:`visible_tickets_condition` (one place):

* ``tickets:read_all`` (IT) — every live ticket;
* ``tickets:read_own`` — tickets the user requested.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import ColumnElement, case, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.permissions import P
from app.core.principal import CurrentUser
from app.models.identity import Permission, Role, User, UserRole, role_permissions
from app.models.task import TaskPriority
from app.models.ticket import (
    OPEN_TICKET_STATUSES,
    Ticket,
    TicketAttachment,
    TicketComment,
    TicketEvent,
)
from app.schemas.tickets import TicketScope, TicketSort


def visible_tickets_condition(user: CurrentUser) -> ColumnElement[bool]:
    live = Ticket.deleted_at.is_(None)
    if user.has(P.TICKETS_READ_ALL):
        return live
    if user.has(P.TICKETS_READ_OWN):
        return live & (Ticket.requester_id == user.id)
    return false()


@dataclass(frozen=True, slots=True)
class TicketFilters:
    scope: TicketScope = "mine"
    q: str | None = None
    status: str | None = None
    open_only: bool = False
    category: str | None = None
    priority: str | None = None


@dataclass(frozen=True, slots=True)
class TicketRow:
    ticket: Ticket
    requester_name: str
    assignee_name: str | None


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


_PRIORITY_RANK = case({p.value: p.rank for p in TaskPriority}, value=Ticket.priority)


def _base(user: CurrentUser) -> Any:
    requester = aliased(User)
    assignee = aliased(User)
    return (
        select(Ticket, requester.display_name, assignee.display_name)
        .join(requester, requester.id == Ticket.requester_id)
        .outerjoin(assignee, assignee.id == Ticket.assignee_id)
        .where(visible_tickets_condition(user))
    )


def _row(row: Sequence[Any]) -> TicketRow:
    return TicketRow(ticket=row[0], requester_name=str(row[1]), assignee_name=row[2])


async def list_tickets(
    session: AsyncSession,
    user: CurrentUser,
    filters: TicketFilters,
    *,
    sort: TicketSort,
    page: int,
    page_size: int,
) -> tuple[list[TicketRow], int]:
    stmt = _base(user)
    if filters.scope == "mine":
        stmt = stmt.where(Ticket.requester_id == user.id)
    elif filters.scope == "assigned":
        stmt = stmt.where(Ticket.assignee_id == user.id)
    elif filters.scope == "unassigned":
        stmt = stmt.where(Ticket.assignee_id.is_(None))
    if filters.q:
        pattern = f"%{_escape_like(filters.q.strip())}%"
        stmt = stmt.where(
            or_(
                Ticket.title.ilike(pattern, escape="\\"),
                Ticket.ticket_number.ilike(pattern, escape="\\"),
            )
        )
    if filters.status:
        stmt = stmt.where(Ticket.status == filters.status)
    if filters.open_only:
        stmt = stmt.where(Ticket.status.in_(OPEN_TICKET_STATUSES))
    if filters.category:
        stmt = stmt.where(Ticket.category == filters.category)
    if filters.priority:
        stmt = stmt.where(Ticket.priority == filters.priority)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order: tuple[Any, ...] = {
        "updated": (Ticket.updated_at.desc(), Ticket.id.desc()),
        "created": (Ticket.created_at.desc(), Ticket.id.desc()),
        "priority": (_PRIORITY_RANK.desc(), Ticket.created_at.asc(), Ticket.id),
    }[sort]
    rows = await session.execute(
        stmt.order_by(*order).offset((page - 1) * page_size).limit(page_size)
    )
    return [_row(r) for r in rows], int(total)


async def get_ticket(
    session: AsyncSession, user: CurrentUser, ticket_id: uuid.UUID
) -> TicketRow | None:
    row = (await session.execute(_base(user).where(Ticket.id == ticket_id))).first()
    return _row(row) if row else None


async def get_for_update(session: AsyncSession, ticket_id: uuid.UUID) -> Ticket | None:
    stmt = (
        select(Ticket).where(Ticket.id == ticket_id, Ticket.deleted_at.is_(None)).with_for_update()
    )
    return await session.scalar(stmt)


async def next_number(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.nextval("ticket_number_seq"))) or 0)


def _holders(permission: str) -> Any:
    return (
        select(UserRole.user_id)
        .join(Role, Role.id == UserRole.role_id)
        .join(role_permissions, role_permissions.c.role_id == Role.id)
        .join(Permission, Permission.id == role_permissions.c.permission_id)
        .where(Permission.code == permission)
    )


async def users_with_permission(
    session: AsyncSession, permission: str, *, q: str | None = None, limit: int = 100
) -> Sequence[User]:
    """Active users holding ``permission`` (IT staff for assignment, leads for new tickets)."""
    stmt = select(User).where(
        User.id.in_(_holders(permission)), User.deleted_at.is_(None), User.is_active.is_(True)
    )
    if q and q.strip():
        stmt = stmt.where(User.display_name.ilike(f"%{_escape_like(q.strip())}%", escape="\\"))
    return (await session.scalars(stmt.order_by(User.display_name).limit(limit))).all()


async def has_permission(session: AsyncSession, user_id: uuid.UUID, permission: str) -> bool:
    stmt = _holders(permission).where(UserRole.user_id == user_id).limit(1)
    return (await session.scalar(stmt)) is not None


async def list_comments(
    session: AsyncSession, ticket_id: uuid.UUID, *, include_internal: bool
) -> list[tuple[TicketComment, str | None]]:
    stmt = (
        select(TicketComment, User.display_name)
        .outerjoin(User, User.id == TicketComment.author_id)
        .where(TicketComment.ticket_id == ticket_id)
        .order_by(TicketComment.created_at, TicketComment.id)
    )
    if not include_internal:
        stmt = stmt.where(TicketComment.is_internal.is_(False))
    return [(r[0], r[1]) for r in await session.execute(stmt)]


async def list_events(
    session: AsyncSession, ticket_id: uuid.UUID, *, include_internal: bool
) -> list[tuple[TicketEvent, str | None]]:
    stmt = (
        select(TicketEvent, User.display_name)
        .outerjoin(User, User.id == TicketEvent.actor_id)
        .where(TicketEvent.ticket_id == ticket_id)
        .order_by(TicketEvent.created_at.desc(), TicketEvent.id.desc())
        .limit(200)
    )
    if not include_internal:
        stmt = stmt.where(TicketEvent.is_internal.is_(False))
    return [(r[0], r[1]) for r in await session.execute(stmt)]


async def list_attachments(
    session: AsyncSession, ticket_id: uuid.UUID, *, include_internal: bool
) -> list[tuple[TicketAttachment, str | None]]:
    stmt = (
        select(TicketAttachment, User.display_name)
        .outerjoin(User, User.id == TicketAttachment.uploaded_by)
        .where(TicketAttachment.ticket_id == ticket_id)
        .order_by(TicketAttachment.created_at, TicketAttachment.id)
    )
    if not include_internal:
        stmt = stmt.where(TicketAttachment.is_internal.is_(False))
    return [(r[0], r[1]) for r in await session.execute(stmt)]


async def get_attachment(
    session: AsyncSession, ticket_id: uuid.UUID, attachment_id: uuid.UUID
) -> TicketAttachment | None:
    return await session.scalar(
        select(TicketAttachment).where(
            TicketAttachment.id == attachment_id, TicketAttachment.ticket_id == ticket_id
        )
    )


async def count_attachments(session: AsyncSession, ticket_id: uuid.UUID) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(TicketAttachment)
            .where(TicketAttachment.ticket_id == ticket_id)
        )
        or 0
    )
