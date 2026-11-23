"""Company announcements (ADR-067). Reading needs only a session; writing needs
``announcements:manage``."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import CurrentUserDep, DbDep, MetaDep, require_permissions
from app.core.permissions import P
from app.core.principal import CurrentUser
from app.schemas.announcements import (
    AnnouncementCreate,
    AnnouncementList,
    AnnouncementOut,
    AnnouncementUnread,
    AnnouncementUpdate,
)
from app.services import announcements as service

router = APIRouter(prefix="/announcements", tags=["announcements"])

Manager = Annotated[CurrentUser, Depends(require_permissions(P.ANNOUNCEMENTS_MANAGE))]


@router.get("", response_model=AnnouncementList, summary="Announcements for me (pinned first)")
async def list_announcements(
    db: DbDep,
    user: CurrentUserDep,
    include_expired: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> AnnouncementList:
    return await service.list_announcements(db, user, include_expired=include_expired, limit=limit)


@router.get("/unread-count", response_model=AnnouncementUnread, summary="Unread announcements")
async def unread_count(db: DbDep, user: CurrentUserDep) -> AnnouncementUnread:
    return AnnouncementUnread(unread_count=await service.unread_count(db, user))


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT, summary="Mark all as read")
async def mark_all_read(db: DbDep, user: CurrentUserDep) -> Response:
    await service.mark_all_read(db, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{announcement_id}", response_model=AnnouncementOut, summary="One announcement")
async def get_announcement(
    announcement_id: uuid.UUID, db: DbDep, user: CurrentUserDep
) -> AnnouncementOut:
    return await service.get_announcement(db, user, announcement_id)


@router.post("/{announcement_id}/read", response_model=AnnouncementUnread, summary="Mark as read")
async def mark_read(
    announcement_id: uuid.UUID, db: DbDep, user: CurrentUserDep
) -> AnnouncementUnread:
    return AnnouncementUnread(unread_count=await service.mark_read(db, user, announcement_id))


@router.post(
    "",
    response_model=AnnouncementOut,
    status_code=status.HTTP_201_CREATED,
    summary="Publish an announcement",
)
async def create_announcement(
    body: AnnouncementCreate, db: DbDep, user: Manager, meta: MetaDep
) -> AnnouncementOut:
    return await service.create_announcement(db, user, body, meta)


@router.patch("/{announcement_id}", response_model=AnnouncementOut, summary="Edit")
async def update_announcement(
    announcement_id: uuid.UUID,
    body: AnnouncementUpdate,
    db: DbDep,
    user: Manager,
    meta: MetaDep,
) -> AnnouncementOut:
    return await service.update_announcement(db, user, announcement_id, body, meta)


@router.delete("/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete")
async def delete_announcement(
    announcement_id: uuid.UUID, db: DbDep, user: Manager, meta: MetaDep
) -> Response:
    await service.delete_announcement(db, user, announcement_id, meta)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
