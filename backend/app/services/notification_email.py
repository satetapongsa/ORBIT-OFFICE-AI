"""E-mail delivery of committed notifications (runs in the worker).

Each notification is mailed once at most, to the user's account address, when the user
wants e-mail for its type (``notification_preferences`` or the defaults) and SMTP is
configured. Outcomes are stored on the notification (``email_status``).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.mail import MailError, mail_enabled, send_mail
from app.core.security import utcnow
from app.models.identity import User
from app.models.notification import (
    EMAIL_DEFAULTS,
    EmailStatus,
    Notification,
    NotificationPreference,
    NotificationType,
)

logger = get_logger(__name__)


def _wants_email(session: Session, user_id: uuid.UUID, kind: str) -> bool:
    chosen = session.scalar(
        select(NotificationPreference.email_enabled).where(
            NotificationPreference.user_id == user_id, NotificationPreference.type == kind
        )
    )
    return chosen if chosen is not None else EMAIL_DEFAULTS[NotificationType(kind)]


def render(settings: Settings, notification: Notification, display_name: str) -> tuple[str, str]:
    base = settings.frontend_base_url.rstrip("/")
    lines = [f"เรียน คุณ{display_name}", "", notification.title]
    if notification.body:
        lines += ["", notification.body]
    if notification.link_url:
        lines += ["", f"เปิดดูในระบบ: {base}{notification.link_url}"]
    lines += [
        "",
        "—",
        "อีเมลนี้ส่งอัตโนมัติจาก AURA OFFICE AI",
        f"ตั้งค่าการแจ้งเตือนทางอีเมลได้ที่ {base}/account",
    ]
    return f"[AURA] {notification.title}", "\n".join(lines)


def send_notification_emails(
    session: Session, settings: Settings, ids: list[uuid.UUID]
) -> dict[str, int]:
    counts = {status.value: 0 for status in EmailStatus}
    for notification_id in ids:
        row = session.execute(
            select(Notification, User)
            .join(User, User.id == Notification.user_id)
            .where(Notification.id == notification_id)
            .with_for_update(of=Notification)
        ).first()
        if row is None:
            continue
        notification, user = row
        if notification.email_status in (EmailStatus.SENT.value, EmailStatus.SKIPPED.value):
            session.rollback()
            continue  # already handled (redelivered task)
        if (
            not mail_enabled(settings)
            or not user.is_active
            or user.deleted_at is not None
            or not _wants_email(session, user.id, notification.type)
        ):
            status = EmailStatus.SKIPPED
        else:
            subject, text = render(settings, notification, user.display_name)
            try:
                send_mail(settings, to=user.email, subject=subject, text=text)
                status = EmailStatus.SENT
                notification.emailed_at = utcnow()
            except MailError:
                status = EmailStatus.FAILED
        notification.email_status = status.value
        counts[status.value] += 1
        session.commit()
    logger.info("notification_emails_processed", **counts)
    return counts
