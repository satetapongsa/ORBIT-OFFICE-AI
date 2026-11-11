"""In-app notifications.

Producers call :func:`notify` (or one of the helpers below) inside their own transaction, so a
notification exists exactly when the change that caused it was committed. Readers only ever
see their own notifications.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.security import utcnow
from app.models.notification import Notification, NotificationType
from app.repositories import notifications as notification_repo

ACCOUNT_LINK = "/account"

# Human-readable field names for "your account was updated" messages.
_FIELD_LABELS = {
    "employee_code": "รหัสพนักงาน",
    "email": "อีเมล",
    "first_name": "ชื่อ",
    "last_name": "นามสกุล",
    "display_name": "ชื่อที่แสดง",
    "department_id": "แผนก",
    "job_title": "ตำแหน่ง",
    "phone_work": "เบอร์โทรที่ทำงาน",
    "employment_status": "สถานะการจ้างงาน",
}


def _safe_link(link_url: str | None) -> str | None:
    if link_url is None:
        return None
    if not link_url.startswith("/") or link_url.startswith("//") or "\\" in link_url:
        raise ValueError("notification links must be relative in-app paths")
    return link_url


def notify(
    session: AsyncSession | Session,
    *,
    user_id: uuid.UUID,
    type: NotificationType,
    title: str,
    body: str = "",
    link_url: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
) -> Notification:
    """Add a notification to the caller's transaction (committed together with the change)."""
    entry = Notification(
        user_id=user_id,
        type=type.value,
        title=title[:200],
        body=body,
        link_url=_safe_link(link_url),
        entity_type=entity_type,
        entity_id=entity_id,
    )
    session.add(entry)
    return entry


# --- Producers used by the identity services -------------------------------------------


def welcome(session: AsyncSession | Session, user_id: uuid.UUID) -> Notification:
    return notify(
        session,
        user_id=user_id,
        type=NotificationType.ACCOUNT,
        title="ยินดีต้อนรับสู่ AURA OFFICE AI",
        body="บัญชีของคุณพร้อมใช้งานแล้ว ตรวจสอบข้อมูลบัญชีและเปลี่ยนรหัสผ่านได้ที่หน้าบัญชีของฉัน",
        link_url=ACCOUNT_LINK,
        entity_type="user",
        entity_id=user_id,
    )


def password_changed(session: AsyncSession, user_id: uuid.UUID, *, via_reset: bool) -> None:
    notify(
        session,
        user_id=user_id,
        type=NotificationType.SECURITY,
        title="รีเซ็ตรหัสผ่านสำเร็จ" if via_reset else "รหัสผ่านของคุณถูกเปลี่ยนแล้ว",
        body=("ระบบได้ออกจากระบบอุปกรณ์อื่นทั้งหมดแล้ว หากคุณไม่ได้ทำรายการนี้ กรุณาติดต่อฝ่ายไอทีทันที"),
        link_url=ACCOUNT_LINK,
        entity_type="user",
        entity_id=user_id,
    )


def suspicious_session(session: AsyncSession, user_id: uuid.UUID) -> None:
    notify(
        session,
        user_id=user_id,
        type=NotificationType.SECURITY,
        title="ตรวจพบการใช้งานเซสชันที่ผิดปกติ",
        body=(
            "มีการนำโทเคนเข้าสู่ระบบเดิมกลับมาใช้ซ้ำ ระบบจึงยกเลิกเซสชันนั้นเพื่อความปลอดภัย "
            "หากเกิดซ้ำบ่อย แนะนำให้เปลี่ยนรหัสผ่าน"
        ),
        link_url=ACCOUNT_LINK,
        entity_type="user",
        entity_id=user_id,
    )


def roles_changed(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    added: Iterable[str],
    removed: Iterable[str],
) -> None:
    parts: list[str] = []
    added_names = sorted(added)
    removed_names = sorted(removed)
    if added_names:
        parts.append("ได้รับบทบาท: " + ", ".join(added_names))
    if removed_names:
        parts.append("ถูกถอนบทบาท: " + ", ".join(removed_names))
    if not parts:
        return
    notify(
        session,
        user_id=user_id,
        type=NotificationType.ACCOUNT,
        title="บทบาทและสิทธิ์ของคุณมีการเปลี่ยนแปลง",
        body=" · ".join(parts),
        link_url=ACCOUNT_LINK,
        entity_type="user",
        entity_id=user_id,
    )


def account_updated(session: AsyncSession, user_id: uuid.UUID, fields: Sequence[str]) -> None:
    labels = [_FIELD_LABELS.get(f, f) for f in fields]
    if not labels:
        return
    notify(
        session,
        user_id=user_id,
        type=NotificationType.ACCOUNT,
        title="ข้อมูลบัญชีของคุณถูกปรับปรุง",
        body="รายการที่เปลี่ยน: " + ", ".join(labels),
        link_url=ACCOUNT_LINK,
        entity_type="user",
        entity_id=user_id,
    )


def account_reactivated(session: AsyncSession, user_id: uuid.UUID) -> None:
    notify(
        session,
        user_id=user_id,
        type=NotificationType.ACCOUNT,
        title="บัญชีของคุณเปิดใช้งานอีกครั้ง",
        body="คุณสามารถเข้าสู่ระบบและใช้งานได้ตามปกติ",
        link_url=ACCOUNT_LINK,
        entity_type="user",
        entity_id=user_id,
    )


def document_shared(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    document_id: uuid.UUID,
    title: str,
    level_label: str,
    shared_by: str,
) -> None:
    notify(
        session,
        user_id=user_id,
        type=NotificationType.DOCUMENT,
        title=f"มีการแชร์เอกสารให้คุณ: {title}",
        body=f"{shared_by} ให้สิทธิ์{level_label}",
        link_url=f"/documents/{document_id}",
        entity_type="document",
        entity_id=document_id,
    )


def _task_link(task_id: uuid.UUID) -> str:
    return f"/tasks/{task_id}"


def task_assigned(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    task_id: uuid.UUID,
    title: str,
    assigned_by: str,
) -> None:
    notify(
        session,
        user_id=user_id,
        type=NotificationType.TASK,
        title=f"คุณได้รับมอบหมายงาน: {title}",
        body=f"{assigned_by} มอบหมายงานนี้ให้คุณ",
        link_url=_task_link(task_id),
        entity_type="task",
        entity_id=task_id,
    )


def task_status_changed(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    task_id: uuid.UUID,
    title: str,
    status_label: str,
    changed_by: str,
) -> None:
    notify(
        session,
        user_id=user_id,
        type=NotificationType.TASK,
        title=f"งาน{status_label}: {title}",
        body=f"{changed_by} เปลี่ยนสถานะเป็น {status_label}",
        link_url=_task_link(task_id),
        entity_type="task",
        entity_id=task_id,
    )


def task_commented(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    task_id: uuid.UUID,
    title: str,
    author: str,
    excerpt: str,
) -> None:
    short = excerpt if len(excerpt) <= 140 else excerpt[:139] + "…"
    notify(
        session,
        user_id=user_id,
        type=NotificationType.TASK,
        title=f"ความคิดเห็นใหม่ในงาน: {title}",
        body=f"{author}: {short}",
        link_url=_task_link(task_id),
        entity_type="task",
        entity_id=task_id,
    )


# --- Reader operations -------------------------------------------------------------------


async def mark_read(
    session: AsyncSession, user_id: uuid.UUID, notification_id: uuid.UUID
) -> Notification:
    entry = await notification_repo.get_for_user(session, user_id, notification_id)
    if entry is None:
        raise NotFoundError("ไม่พบการแจ้งเตือนนี้")
    if entry.read_at is None:
        entry.read_at = utcnow()
        await session.commit()
    return entry


async def mark_all_read(session: AsyncSession, user_id: uuid.UUID) -> int:
    updated = await notification_repo.mark_all_read(session, user_id, utcnow())
    await session.commit()
    return updated
