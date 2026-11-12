"""Retention and clean-up jobs (Phase 9, ADR-051).

Run daily by Celery beat (`maintenance.purge`) or by hand with ``python -m app.cli purge
[--dry-run]``. Every step is idempotent and safe to repeat; a dry run only counts.

* deleted documents: documents soft-deleted more than ``DOCUMENT_PURGE_AFTER_DAYS`` ago -
  first their stored files, then the rows (versions, text, chunks and ACL cascade);
* orphaned objects: stored files that no document version, task or ticket attachment refers to,
  older than ``STORAGE_ORPHAN_GRACE_HOURS`` (failed uploads, removed attachments);
* chats: sessions deleted by their owner or idle longer than ``AI_CHAT_RETENTION_DAYS``
  (messages and action requests cascade);
* sign-in data: refresh sessions and reset tokens expired, revoked or used more than
  ``SESSION_PURGE_AFTER_DAYS`` ago;
* notifications: read notifications older than ``NOTIFICATION_RETENTION_DAYS``.

Audit logs are never purged (append-only by design).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

from botocore.exceptions import ClientError
from sqlalchemy import ColumnElement, delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.security import utcnow
from app.core.storage import ObjectStorage
from app.models.ai import ChatSession
from app.models.auth import PasswordResetToken, UserSession
from app.models.document import Document, DocumentVersion
from app.models.notification import Notification
from app.models.task import TaskAttachment
from app.models.ticket import TicketAttachment

logger = get_logger(__name__)


@dataclass(slots=True)
class PurgeReport:
    documents: int = 0
    document_objects: int = 0
    orphaned_objects: int = 0
    chat_sessions: int = 0
    auth_sessions: int = 0
    reset_tokens: int = 0
    notifications: int = 0
    errors: int = 0
    dry_run: bool = False

    def as_dict(self) -> dict[str, int | bool]:
        return asdict(self)


def _delete_object(storage: ObjectStorage, key: str) -> bool:
    """True when the object is gone (deleted now or already missing)."""
    try:
        storage.delete_object(key)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"NoSuchKey", "404", "NotFound"}:
            return True
        logger.warning("purge_object_failed", key=key, error=code)
        return False
    return True


def purge_deleted_documents(
    session: Session, storage: ObjectStorage, cutoff: datetime, report: PurgeReport
) -> None:
    rows = session.scalars(
        select(Document.id).where(Document.deleted_at.is_not(None), Document.deleted_at < cutoff)
    ).all()
    for document_id in rows:
        keys = session.scalars(
            select(DocumentVersion.storage_key).where(DocumentVersion.document_id == document_id)
        ).all()
        if report.dry_run:
            report.documents += 1
            report.document_objects += len(keys)
            continue
        removed = [k for k in keys if _delete_object(storage, k)]
        report.document_objects += len(removed)
        if len(removed) != len(keys):
            # Keep the row so the remaining files are retried next run (never orphan them).
            report.errors += 1
            continue
        session.execute(delete(Document).where(Document.id == document_id))
        session.commit()
        report.documents += 1


def purge_orphaned_objects(
    session: Session, storage: ObjectStorage, cutoff: datetime, report: PurgeReport
) -> None:
    referenced = set(session.scalars(select(DocumentVersion.storage_key)).all())
    referenced |= set(session.scalars(select(TaskAttachment.storage_key)).all())
    referenced |= set(session.scalars(select(TicketAttachment.storage_key)).all())
    for obj in storage.iter_objects():
        if obj.key in referenced or obj.last_modified >= cutoff:
            continue
        if report.dry_run or _delete_object(storage, obj.key):
            report.orphaned_objects += 1
        else:
            report.errors += 1


def _count_or_delete(
    session: Session, model: type[Any], condition: ColumnElement[bool], dry_run: bool
) -> int:
    if dry_run:
        return int(session.scalar(select(func.count()).select_from(model).where(condition)) or 0)
    result = session.execute(delete(model).where(condition))
    session.commit()
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def purge(
    session: Session,
    storage: ObjectStorage,
    settings: Settings,
    *,
    dry_run: bool = False,
    now: datetime | None = None,
) -> PurgeReport:
    now = now or utcnow()
    report = PurgeReport(dry_run=dry_run)

    purge_deleted_documents(
        session, storage, now - timedelta(days=settings.document_purge_after_days), report
    )
    # After the document step, so files of documents purged just now are not counted twice.
    purge_orphaned_objects(
        session, storage, now - timedelta(hours=settings.storage_orphan_grace_hours), report
    )

    chats = now - timedelta(days=settings.ai_chat_retention_days)
    report.chat_sessions = _count_or_delete(
        session,
        ChatSession,
        or_(ChatSession.deleted_at.is_not(None), ChatSession.last_message_at < chats),
        dry_run,
    )

    auth = now - timedelta(days=settings.session_purge_after_days)
    report.auth_sessions = _count_or_delete(
        session,
        UserSession,
        or_(
            UserSession.expires_at < auth,
            UserSession.family_expires_at < auth,
            UserSession.revoked_at < auth,
        ),
        dry_run,
    )
    report.reset_tokens = _count_or_delete(
        session,
        PasswordResetToken,
        or_(PasswordResetToken.expires_at < auth, PasswordResetToken.used_at < auth),
        dry_run,
    )

    notes = now - timedelta(days=settings.notification_retention_days)
    report.notifications = _count_or_delete(
        session,
        Notification,
        Notification.read_at.is_not(None) & (Notification.created_at < notes),
        dry_run,
    )
    logger.info("purge_finished", **report.as_dict())
    return report
