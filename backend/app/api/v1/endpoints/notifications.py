"""The signed-in user's own notifications. No extra permission: users only see their own."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUserDep, DbDep, SettingsDep
from app.core.mail import mail_enabled
from app.models.notification import EMAIL_DEFAULTS
from app.repositories import notifications as notification_repo
from app.schemas.notifications import (
    EmailPreferenceOut,
    EmailPreferences,
    EmailPreferencesUpdate,
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


async def _preferences(db: DbDep, settings: SettingsDep, user_id: uuid.UUID) -> EmailPreferences:
    chosen = await notification_service.get_email_preferences(db, user_id)
    return EmailPreferences(
        email_available=mail_enabled(settings),
        items=[
            EmailPreferenceOut(type=kind, email_enabled=enabled, default=EMAIL_DEFAULTS[kind])
            for kind, enabled in chosen.items()
        ],
    )


@router.get("/preferences", response_model=EmailPreferences, summary="My e-mail preferences")
async def get_preferences(
    db: DbDep, settings: SettingsDep, user: CurrentUserDep
) -> EmailPreferences:
    return await _preferences(db, settings, user.id)


@router.put("/preferences", response_model=EmailPreferences, summary="Choose e-mail per type")
async def set_preferences(
    body: EmailPreferencesUpdate, db: DbDep, settings: SettingsDep, user: CurrentUserDep
) -> EmailPreferences:
    await notification_service.set_email_preferences(
        db, user.id, {item.type: item.email_enabled for item in body.items}
    )
    return await _preferences(db, settings, user.id)
