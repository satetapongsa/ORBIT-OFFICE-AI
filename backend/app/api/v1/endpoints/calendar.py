"""Calendar and meetings (ADR-070)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import DbDep, MetaDep, SettingsDep, require_permissions
from app.core.permissions import P
from app.core.principal import CurrentUser
from app.schemas.meetings import (
    AvailabilityOut,
    AvailabilityRequest,
    CalendarFeed,
    MeetingCreate,
    MeetingOut,
    MeetingRespond,
    MeetingUpdate,
)
from app.services import meetings as service

router = APIRouter(prefix="/calendar", tags=["calendar"])

CalendarUser = Annotated[CurrentUser, Depends(require_permissions(P.CALENDAR_USE))]


@router.get("/events", response_model=CalendarFeed, summary="My meetings and team leave")
async def events(
    start: date, end: date, db: DbDep, settings: SettingsDep, user: CalendarUser
) -> CalendarFeed:
    return await service.calendar(db, user, start, end, settings)


@router.post("/availability", response_model=AvailabilityOut, summary="Who is busy then")
async def availability(
    body: AvailabilityRequest, db: DbDep, settings: SettingsDep, user: CalendarUser
) -> AvailabilityOut:
    return await service.availability(
        db, user, body.start_at, body.end_at, body.user_ids, body.exclude_meeting_id, settings
    )


@router.post(
    "/meetings",
    response_model=MeetingOut,
    status_code=status.HTTP_201_CREATED,
    summary="Schedule a meeting and invite people",
)
async def create_meeting(
    body: MeetingCreate, db: DbDep, settings: SettingsDep, user: CalendarUser, meta: MetaDep
) -> MeetingOut:
    return await service.create_meeting(db, user, body, meta, settings)


@router.get("/meetings/{meeting_id}", response_model=MeetingOut, summary="One meeting")
async def get_meeting(meeting_id: uuid.UUID, db: DbDep, user: CalendarUser) -> MeetingOut:
    return await service.get_meeting(db, user, meeting_id)


@router.patch("/meetings/{meeting_id}", response_model=MeetingOut, summary="Change (organizer)")
async def update_meeting(
    meeting_id: uuid.UUID,
    body: MeetingUpdate,
    db: DbDep,
    settings: SettingsDep,
    user: CalendarUser,
    meta: MetaDep,
) -> MeetingOut:
    return await service.update_meeting(db, user, meeting_id, body, meta, settings)


@router.post(
    "/meetings/{meeting_id}/cancel", response_model=MeetingOut, summary="Cancel (organizer)"
)
async def cancel_meeting(
    meeting_id: uuid.UUID, db: DbDep, settings: SettingsDep, user: CalendarUser, meta: MetaDep
) -> MeetingOut:
    return await service.cancel_meeting(db, user, meeting_id, meta, settings)


@router.post(
    "/meetings/{meeting_id}/respond", response_model=MeetingOut, summary="Accept or decline"
)
async def respond(
    meeting_id: uuid.UUID, body: MeetingRespond, db: DbDep, user: CalendarUser
) -> MeetingOut:
    return await service.respond(db, user, meeting_id, body)
