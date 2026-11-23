"""Company announcements (ADR-067).

Everyone signed in reads the announcements meant for them: company-wide ones and those of
their own department. People with ``announcements:manage`` (HR, administrators) write them,
see every announcement (also expired ones) and how many people have read each one.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import ColumnElement, and_, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationFailedError
from app.core.permissions import P
from app.core.principal import CurrentUser, RequestMeta
from app.models.announcement import Announcement, AnnouncementRead
from app.models.identity import Department, User
from app.models.notification import NotificationType
from app.schemas.announcements import (
    AnnouncementCreate,
    AnnouncementList,
    AnnouncementOut,
    AnnouncementUpdate,
)
from app.schemas.common import ErrorDetail
from app.services import audit, notifications
from app.services.audit import AuditAction

NOT_FOUND = "ไม่พบประกาศนี้"
LINK = "/announcements"


def _can_manage(user: CurrentUser) -> bool:
    return user.has(P.ANNOUNCEMENTS_MANAGE)


def _visible(user: CurrentUser) -> ColumnElement[bool]:
    if _can_manage(user):
        return Announcement.id.is_not(None)
    audience: ColumnElement[bool] = Announcement.department_id.is_(None)
    if user.department_id is not None:
        audience = or_(audience, Announcement.department_id == user.department_id)
    return and_(audience, Announcement.published_at <= func.now())


def _active() -> ColumnElement[bool]:
    return and_(
        Announcement.published_at <= func.now(),
        or_(Announcement.expires_at.is_(None), Announcement.expires_at > func.now()),
    )


def _audience_users(department_id: uuid.UUID | None) -> ColumnElement[bool]:
    live = and_(User.is_active.is_(True), User.deleted_at.is_(None))
    return live if department_id is None else and_(live, User.department_id == department_id)


async def _check_department(session: AsyncSession, department_id: uuid.UUID | None) -> None:
    if department_id is None:
        return
    found = await session.scalar(
        select(Department.id).where(Department.id == department_id, Department.deleted_at.is_(None))
    )
    if found is None:
        raise ValidationFailedError(
            details=[ErrorDetail(field="department_id", message="ไม่พบแผนกนี้")]
        )


async def _outs(
    session: AsyncSession, user: CurrentUser, rows: Sequence[Announcement]
) -> list[AnnouncementOut]:
    if not rows:
        return []
    ids = [a.id for a in rows]
    read_ids = set(
        (
            await session.scalars(
                select(AnnouncementRead.announcement_id).where(
                    AnnouncementRead.user_id == user.id,
                    AnnouncementRead.announcement_id.in_(ids),
                )
            )
        ).all()
    )
    names = dict(
        (
            await session.execute(
                select(User.id, User.display_name).where(
                    User.id.in_([a.author_id for a in rows if a.author_id])
                )
            )
        ).all()
    )
    departments = dict(
        (
            await session.execute(
                select(Department.id, Department.name).where(
                    Department.id.in_([a.department_id for a in rows if a.department_id])
                )
            )
        ).all()
    )
    now = await session.scalar(select(func.now()))
    read_counts: dict[uuid.UUID, int] = {}
    audience: dict[uuid.UUID | None, int] = {}
    if _can_manage(user):
        read_counts = dict(
            (
                await session.execute(
                    select(AnnouncementRead.announcement_id, func.count())
                    .join(User, User.id == AnnouncementRead.user_id)
                    .join(Announcement, Announcement.id == AnnouncementRead.announcement_id)
                    .where(
                        AnnouncementRead.announcement_id.in_(ids),
                        User.is_active.is_(True),
                        User.deleted_at.is_(None),
                        # Only readers in the audience count (not e.g. the HR author).
                        or_(
                            Announcement.department_id.is_(None),
                            User.department_id == Announcement.department_id,
                        ),
                    )
                    .group_by(AnnouncementRead.announcement_id)
                )
            ).all()
        )
        for department_id in {a.department_id for a in rows}:
            audience[department_id] = int(
                await session.scalar(
                    select(func.count()).select_from(User).where(_audience_users(department_id))
                )
                or 0
            )
    return [
        AnnouncementOut(
            id=a.id,
            title=a.title,
            body=a.body,
            important=a.important,
            pinned=a.pinned,
            department_id=a.department_id,
            department_name=departments.get(a.department_id) if a.department_id else None,
            author_name=names.get(a.author_id) if a.author_id else None,
            published_at=a.published_at,
            expires_at=a.expires_at,
            expired=a.expires_at is not None and now is not None and a.expires_at <= now,
            edited=(a.updated_at - a.created_at).total_seconds() > 1,
            is_read=a.id in read_ids,
            read_count=int(read_counts.get(a.id, 0)) if _can_manage(user) else None,
            audience_count=audience.get(a.department_id) if _can_manage(user) else None,
        )
        for a in rows
    ]


async def unread_count(session: AsyncSession, user: CurrentUser) -> int:
    read = select(AnnouncementRead.announcement_id).where(AnnouncementRead.user_id == user.id)
    count = await session.scalar(
        select(func.count())
        .select_from(Announcement)
        .where(_visible(user), _active(), Announcement.id.not_in(read))
    )
    return int(count or 0)


async def list_announcements(
    session: AsyncSession, user: CurrentUser, *, include_expired: bool, limit: int
) -> AnnouncementList:
    stmt = select(Announcement).where(_visible(user))
    if not (include_expired and _can_manage(user)):
        stmt = stmt.where(_active())
    rows = (
        await session.scalars(
            stmt.order_by(Announcement.pinned.desc(), Announcement.published_at.desc()).limit(limit)
        )
    ).all()
    return AnnouncementList(
        items=await _outs(session, user, rows), unread_count=await unread_count(session, user)
    )


async def _get_visible(
    session: AsyncSession, user: CurrentUser, announcement_id: uuid.UUID
) -> Announcement:
    found = await session.scalar(
        select(Announcement).where(Announcement.id == announcement_id, _visible(user))
    )
    if found is None:
        raise NotFoundError(NOT_FOUND)
    return found


async def get_announcement(
    session: AsyncSession, user: CurrentUser, announcement_id: uuid.UUID
) -> AnnouncementOut:
    return (await _outs(session, user, [await _get_visible(session, user, announcement_id)]))[0]


async def mark_read(session: AsyncSession, user: CurrentUser, announcement_id: uuid.UUID) -> int:
    await _get_visible(session, user, announcement_id)
    await session.execute(
        insert(AnnouncementRead)
        .values(announcement_id=announcement_id, user_id=user.id)
        .on_conflict_do_nothing()
    )
    await session.commit()
    return await unread_count(session, user)


async def mark_all_read(session: AsyncSession, user: CurrentUser) -> None:
    ids = (await session.scalars(select(Announcement.id).where(_visible(user), _active()))).all()
    if ids:
        await session.execute(
            insert(AnnouncementRead)
            .values([{"announcement_id": i, "user_id": user.id} for i in ids])
            .on_conflict_do_nothing()
        )
        await session.commit()


async def create_announcement(
    session: AsyncSession, user: CurrentUser, data: AnnouncementCreate, meta: RequestMeta
) -> AnnouncementOut:
    await _check_department(session, data.department_id)
    now = await session.scalar(select(func.now()))
    if data.expires_at is not None and now is not None and data.expires_at <= now:
        raise ValidationFailedError(
            details=[ErrorDetail(field="expires_at", message="วันหมดอายุต้องอยู่ในอนาคต")]
        )
    item = Announcement(
        title=data.title,
        body=data.body,
        important=data.important,
        pinned=data.pinned,
        department_id=data.department_id,
        author_id=user.id,
        expires_at=data.expires_at,
    )
    session.add(item)
    await session.flush()
    session.add(
        AnnouncementRead(announcement_id=item.id, user_id=user.id)
    )  # the author has read it
    if data.notify:
        recipients = (
            await session.scalars(
                select(User.id).where(_audience_users(data.department_id), User.id != user.id)
            )
        ).all()
        prefix = "ประกาศสำคัญ: " if data.important else "ประกาศใหม่: "
        for recipient in recipients:
            notifications.notify(
                session,
                user_id=recipient,
                type=NotificationType.ANNOUNCEMENT,
                title=prefix + data.title,
                body=data.body[:200],
                link_url=f"{LINK}?id={item.id}",
                entity_type="announcement",
                entity_id=item.id,
            )
    audit.record(
        session,
        AuditAction.ANNOUNCEMENT_CREATED,
        actor_id=user.id,
        meta=meta,
        entity_type="announcement",
        entity_id=item.id,
        details={"title": data.title, "department_id": str(data.department_id or "")},
    )
    await session.commit()
    await session.refresh(item)
    return (await _outs(session, user, [item]))[0]


async def update_announcement(
    session: AsyncSession,
    user: CurrentUser,
    announcement_id: uuid.UUID,
    data: AnnouncementUpdate,
    meta: RequestMeta,
) -> AnnouncementOut:
    item = await _get_visible(session, user, announcement_id)
    changes = data.model_dump(exclude_unset=True, exclude={"whole_company", "clear_expiry"})
    if data.whole_company:
        changes["department_id"] = None
    elif "department_id" in changes:
        await _check_department(session, changes["department_id"])
    if data.clear_expiry:
        changes["expires_at"] = None
    for field, value in changes.items():
        if value is None and field not in {"department_id", "expires_at"}:
            continue
        setattr(item, field, value)
    if item.expires_at is not None and item.expires_at <= item.published_at:
        raise ValidationFailedError(
            details=[ErrorDetail(field="expires_at", message="วันหมดอายุต้องอยู่หลังวันที่ประกาศ")]
        )
    audit.record(
        session,
        AuditAction.ANNOUNCEMENT_UPDATED,
        actor_id=user.id,
        meta=meta,
        entity_type="announcement",
        entity_id=item.id,
        details={"fields": sorted(changes)},
    )
    await session.commit()
    await session.refresh(item)
    return (await _outs(session, user, [item]))[0]


async def delete_announcement(
    session: AsyncSession, user: CurrentUser, announcement_id: uuid.UUID, meta: RequestMeta
) -> None:
    item = await _get_visible(session, user, announcement_id)
    audit.record(
        session,
        AuditAction.ANNOUNCEMENT_DELETED,
        actor_id=user.id,
        meta=meta,
        entity_type="announcement",
        entity_id=item.id,
        details={"title": item.title},
    )
    await session.execute(delete(Announcement).where(Announcement.id == item.id))
    await session.commit()
