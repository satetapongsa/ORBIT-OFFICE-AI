"""Leave requests (ADR-068)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import DbDep, MetaDep, SettingsDep, require_permissions
from app.core.permissions import P
from app.core.principal import CurrentUser
from app.models.leave import HalfDay, LeaveStatus
from app.schemas.leave import (
    LeaveDecision,
    LeavePreview,
    LeaveRequestCreate,
    LeaveRequestOut,
    LeaveScope,
    LeaveTypeOut,
    LeaveTypeUpdate,
    MyLeave,
    QuotaUpdate,
)
from app.services import leave as service

router = APIRouter(prefix="/leave", tags=["leave"])

Requester = Annotated[CurrentUser, Depends(require_permissions(P.LEAVE_REQUEST))]
Manager = Annotated[CurrentUser, Depends(require_permissions(P.LEAVE_MANAGE))]


@router.get("/types", response_model=list[LeaveTypeOut], summary="Leave types")
async def list_types(
    db: DbDep, user: Requester, include_inactive: bool = False
) -> list[LeaveTypeOut]:
    return await service.list_types(
        db, include_inactive=include_inactive and user.has(P.LEAVE_MANAGE)
    )


@router.patch("/types/{type_id}", response_model=LeaveTypeOut, summary="Change a leave type")
async def update_type(
    type_id: uuid.UUID, body: LeaveTypeUpdate, db: DbDep, user: Manager, meta: MetaDep
) -> LeaveTypeOut:
    return await service.update_type(db, user, type_id, body, meta)


@router.put("/quotas", status_code=status.HTTP_204_NO_CONTENT, summary="Set a person's quota")
async def set_quota(body: QuotaUpdate, db: DbDep, user: Manager, meta: MetaDep) -> Response:
    await service.set_quota(db, user, body, meta)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/balances/{user_id}", summary="A person's balances (HR)")
async def user_balances(
    user_id: uuid.UUID,
    db: DbDep,
    settings: SettingsDep,
    user: Manager,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
) -> list[service.LeaveBalance]:
    return await service.balances(db, user_id, year or service.today(settings).year)


@router.get("/preview", response_model=LeavePreview, summary="Working days in a period")
async def preview(
    start_date: date, end_date: date, user: Requester, half_day: HalfDay = HalfDay.NONE
) -> LeavePreview:
    return LeavePreview(days=service.working_days(start_date, end_date, half_day))


@router.get("/me", response_model=MyLeave, summary="My balances and requests for a year")
async def my_leave(
    db: DbDep,
    settings: SettingsDep,
    user: Requester,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
) -> MyLeave:
    return await service.my_leave(db, user, settings, year)


@router.post(
    "/requests",
    response_model=LeaveRequestOut,
    status_code=status.HTTP_201_CREATED,
    summary="Request leave",
)
async def create_request(
    body: LeaveRequestCreate, db: DbDep, settings: SettingsDep, user: Requester, meta: MetaDep
) -> LeaveRequestOut:
    return await service.create_request(db, user, settings, body, meta)


@router.get("/requests", response_model=list[LeaveRequestOut], summary="Requests of others")
async def list_requests(
    db: DbDep,
    settings: SettingsDep,
    user: Requester,
    scope: LeaveScope = "approvals",
    status_filter: Annotated[LeaveStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[LeaveRequestOut]:
    return await service.list_requests(
        db, user, settings, scope=scope, status=status_filter, limit=limit
    )


@router.post(
    "/requests/{request_id}/decision", response_model=LeaveRequestOut, summary="Approve or reject"
)
async def decide(
    request_id: uuid.UUID,
    body: LeaveDecision,
    db: DbDep,
    settings: SettingsDep,
    user: Requester,
    meta: MetaDep,
) -> LeaveRequestOut:
    return await service.decide(db, user, settings, request_id, body, meta)


@router.post("/requests/{request_id}/cancel", response_model=LeaveRequestOut, summary="Cancel")
async def cancel(
    request_id: uuid.UUID, db: DbDep, settings: SettingsDep, user: Requester, meta: MetaDep
) -> LeaveRequestOut:
    return await service.cancel(db, user, settings, request_id, meta)


@router.get("/calendar", response_model=list[LeaveRequestOut], summary="Who is on approved leave")
async def calendar(
    start: date, end: date, db: DbDep, settings: SettingsDep, user: Requester
) -> list[LeaveRequestOut]:
    return await service.team_calendar(db, user, settings, start, end)
