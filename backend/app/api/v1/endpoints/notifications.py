"""The signed-in user's own notifications. No extra permission: users only see their own."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUserDep, DbDep
from app.repositories import notifications as notification_repo
from app.schemas.notifications import (
    MarkAllReadResult,
    NotificationOut,
    NotificationPage,
    UnreadCount,
)
from app.services import notifications as notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationPage, summary="List my notifications (newest first)")
async def list_notifications(
    db: DbDep,
    user: CurrentUserDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    unread_only: bool = False,
) -> NotificationPage:
    rows, total = await notification_repo.list_for_user(
        db, user.id, page=page, page_size=page_size, unread_only=unread_only
    )
    return NotificationPage(
        items=[NotificationOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        unread_count=await notification_repo.count_unread(db, user.id),
    )


@router.get("/unread-count", response_model=UnreadCount, summary="Number of unread notifications")
async def unread_count(db: DbDep, user: CurrentUserDep) -> UnreadCount:
    return UnreadCount(unread_count=await notification_repo.count_unread(db, user.id))


@router.post(
    "/read-all", response_model=MarkAllReadResult, summary="Mark all my notifications as read"
)
async def mark_all_read(db: DbDep, user: CurrentUserDep) -> MarkAllReadResult:
    updated = await notification_service.mark_all_read(db, user.id)
    return MarkAllReadResult(updated=updated, unread_count=0)


@router.post(
    "/{notification_id}/read",
    response_model=NotificationOut,
    summary="Mark one of my notifications as read",
)
async def mark_read(notification_id: uuid.UUID, db: DbDep, user: CurrentUserDep) -> NotificationOut:
    entry = await notification_service.mark_read(db, user.id, notification_id)
    return NotificationOut.model_validate(entry)
