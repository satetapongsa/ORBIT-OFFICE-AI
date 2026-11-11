"""IT helpdesk endpoints (HTTP only — rules live in ``app.services.tickets``)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUserDep, DbDep, MetaDep, SettingsDep, require_permissions
from app.core.errors import PermissionDeniedError
from app.core.permissions import P
from app.core.principal import CurrentUser
from app.models.task import TaskPriority
from app.models.ticket import TicketCategory, TicketStatus
from app.repositories import tickets as ticket_repo
from app.repositories.tickets import TicketFilters
from app.schemas.identity import DepartmentRef
from app.schemas.tasks import AssignableUser
from app.schemas.tickets import (
    TicketAssign,
    TicketCommentIn,
    TicketCommentOut,
    TicketCreate,
    TicketDetail,
    TicketEventOut,
    TicketPage,
    TicketScope,
    TicketSort,
    TicketStatusUpdate,
    TicketUpdate,
)
from app.services.tickets import service as ticket_service

router = APIRouter(prefix="/tickets", tags=["tickets"])


def _require_reader(user: CurrentUser) -> None:
    if not user.has_any((P.TICKETS_READ_OWN, P.TICKETS_READ_ALL)):
        raise PermissionDeniedError("คุณไม่มีสิทธิ์ดูรายการแจ้งปัญหา")


@router.get("", response_model=TicketPage, summary="List tickets I can see")
async def list_tickets(
    db: DbDep,
    user: CurrentUserDep,
    scope: TicketScope = "mine",
    q: Annotated[str | None, Query(max_length=200)] = None,
    status_: Annotated[TicketStatus | None, Query(alias="status")] = None,
    open_only: bool = False,
    category: TicketCategory | None = None,
    priority: TaskPriority | None = None,
    sort: TicketSort = "updated",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> TicketPage:
    _require_reader(user)
    if scope != "mine" and not user.has(P.TICKETS_READ_ALL):
        raise PermissionDeniedError("ขอบเขตนี้สำหรับทีมไอทีเท่านั้น")
    rows, total = await ticket_repo.list_tickets(
        db,
        user,
        TicketFilters(
            scope=scope,
            q=q,
            status=status_.value if status_ else None,
            open_only=open_only,
            category=category.value if category else None,
            priority=priority.value if priority else None,
        ),
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return TicketPage(
        items=[ticket_service.list_item(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "", response_model=TicketDetail, status_code=status.HTTP_201_CREATED, summary="Report a problem"
)
async def create_ticket(
    body: TicketCreate, db: DbDep, settings: SettingsDep, user: CurrentUserDep, meta: MetaDep
) -> TicketDetail:
    ticket_id = await ticket_service.create_ticket(db, settings, user, body, meta)
    return await ticket_service.detail(db, user, ticket_id)


@router.get("/assignees", response_model=list[AssignableUser], summary="IT staff to assign")
async def assignees(
    db: DbDep,
    _: Annotated[CurrentUser, Depends(require_permissions(P.TICKETS_ASSIGN))],
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> list[AssignableUser]:
    return [
        AssignableUser(
            id=u.id,
            display_name=u.display_name,
            job_title=u.job_title,
            department=DepartmentRef.model_validate(u.department) if u.department else None,
        )
        for u in await ticket_repo.users_with_permission(db, P.TICKETS_MANAGE, q=q, limit=50)
    ]


@router.get("/{ticket_id}", response_model=TicketDetail, summary="Ticket details")
async def get_ticket(ticket_id: uuid.UUID, db: DbDep, user: CurrentUserDep) -> TicketDetail:
    _require_reader(user)
    return await ticket_service.detail(db, user, ticket_id)


@router.patch("/{ticket_id}", response_model=TicketDetail, summary="Category / priority (IT)")
async def update_ticket(
    ticket_id: uuid.UUID, body: TicketUpdate, db: DbDep, user: CurrentUserDep, meta: MetaDep
) -> TicketDetail:
    _require_reader(user)
    await ticket_service.update(db, user, ticket_id, body, meta)
    return await ticket_service.detail(db, user, ticket_id)


@router.post("/{ticket_id}/status", response_model=TicketDetail, summary="Change the status")
async def change_status(
    ticket_id: uuid.UUID, body: TicketStatusUpdate, db: DbDep, user: CurrentUserDep, meta: MetaDep
) -> TicketDetail:
    _require_reader(user)
    await ticket_service.change_status(db, user, ticket_id, body.status, meta)
    return await ticket_service.detail(db, user, ticket_id)


@router.put("/{ticket_id}/assignee", response_model=TicketDetail, summary="Assign (IT)")
async def assign_ticket(
    ticket_id: uuid.UUID, body: TicketAssign, db: DbDep, user: CurrentUserDep, meta: MetaDep
) -> TicketDetail:
    _require_reader(user)
    await ticket_service.assign(db, user, ticket_id, body.assignee_id, meta)
    return await ticket_service.detail(db, user, ticket_id)


@router.get("/{ticket_id}/comments", response_model=list[TicketCommentOut], summary="Conversation")
async def list_comments(
    ticket_id: uuid.UUID, db: DbDep, user: CurrentUserDep
) -> list[TicketCommentOut]:
    _require_reader(user)
    return await ticket_service.comments(db, user, ticket_id)


@router.post(
    "/{ticket_id}/comments",
    response_model=list[TicketCommentOut],
    status_code=status.HTTP_201_CREATED,
    summary="Reply (or add an internal note)",
)
async def add_comment(
    ticket_id: uuid.UUID, body: TicketCommentIn, db: DbDep, user: CurrentUserDep
) -> list[TicketCommentOut]:
    _require_reader(user)
    await ticket_service.add_comment(db, user, ticket_id, body.body, body.is_internal)
    return await ticket_service.comments(db, user, ticket_id)


@router.get("/{ticket_id}/history", response_model=list[TicketEventOut], summary="Timeline")
async def history(ticket_id: uuid.UUID, db: DbDep, user: CurrentUserDep) -> list[TicketEventOut]:
    _require_reader(user)
    return await ticket_service.history(db, user, ticket_id)
