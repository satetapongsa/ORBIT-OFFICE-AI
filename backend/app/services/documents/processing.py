"""Text extraction pipeline for one document version (synchronous; runs in the worker).

States: PENDING → PROCESSING → READY | FAILED. The task is idempotent: a READY version is
skipped unless ``force`` is set, so redelivered Celery messages do no harm.
"""

from __future__ import annotations

import tempfile
import uuid
from typing import BinaryIO, Protocol, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.security import utcnow
from app.models.document import (
    Document,
    DocumentVersion,
    DocumentVersionText,
    FileType,
    ProcessingStatus,
)
from app.models.notification import NotificationType
from app.services import notifications
from app.services.documents.extraction import ExtractionError, extract_text

logger = get_logger(__name__)

GENERIC_FAILURE = "ประมวลผลไฟล์ไม่สำเร็จ กรุณาลองใหม่อีกครั้ง หรือติดต่อฝ่ายไอที"
TIMEOUT_FAILURE = "ประมวลผลไฟล์นานเกินกำหนด ไฟล์อาจมีขนาดใหญ่หรือซับซ้อนเกินไป"

# Spool downloads to disk above this size so large files do not sit in worker memory.
_SPOOL_BYTES = 8 * 1024 * 1024


class ObjectReader(Protocol):
    def download_to(self, key: str, fileobj: BinaryIO) -> None: ...


def _load(session: Session, version_id: uuid.UUID) -> tuple[DocumentVersion, Document] | None:
    row = session.execute(
        select(DocumentVersion, Document)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(DocumentVersion.id == version_id)
        .with_for_update(of=DocumentVersion)
    ).first()
    return (row[0], row[1]) if row else None


def mark_failed(
    session: Session, version_id: uuid.UUID, message: str, *, notify_owner: bool = True
) -> None:
    loaded = _load(session, version_id)
    if loaded is None:
        return
    version, document = loaded
    version.processing_status = ProcessingStatus.FAILED.value
    version.processing_error = message[:500]
    version.processed_at = utcnow()
    if notify_owner and version.uploaded_by is not None and document.deleted_at is None:
        notifications.notify(
            session,
            user_id=version.uploaded_by,
            type=NotificationType.DOCUMENT,
            title=f"ประมวลผลเอกสารไม่สำเร็จ: {document.title}",
            body=message,
            link_url=f"/documents/{document.id}",
            entity_type="document",
            entity_id=document.id,
        )
    session.commit()


def process_version(
    session: Session, storage: ObjectReader, version_id: uuid.UUID, *, force: bool = False
) -> str:
    """Extract and store the text of a version. Returns the final processing status."""
    loaded = _load(session, version_id)
    if loaded is None:
        logger.warning("document_version_missing", version_id=str(version_id))
        return "MISSING"
    version, document = loaded
    if document.deleted_at is not None:
        session.rollback()
        return "SKIPPED"
    if version.processing_status == ProcessingStatus.READY.value and not force:
        session.rollback()
        return ProcessingStatus.READY.value

    version.processing_status = ProcessingStatus.PROCESSING.value
    version.processing_error = None
    storage_key, file_type = version.storage_key, FileType(version.file_type)
    session.commit()  # make PROCESSING visible while we work

    try:
        with tempfile.SpooledTemporaryFile(max_size=_SPOOL_BYTES) as buffer:
            stream = cast(BinaryIO, buffer)
            storage.download_to(storage_key, stream)
            result = extract_text(stream, file_type)
    except ExtractionError as exc:
        logger.info("document_extraction_failed", version_id=str(version_id), reason=exc.message)
        mark_failed(session, version_id, exc.message)
        return ProcessingStatus.FAILED.value

    loaded = _load(session, version_id)
    if loaded is None:
        return "MISSING"
    version, _ = loaded
    existing = session.get(DocumentVersionText, version_id)
    if existing is None:
        session.add(DocumentVersionText(document_version_id=version_id, content=result.text))
    else:
        existing.content = result.text
    version.processing_status = ProcessingStatus.READY.value
    version.processing_error = None
    version.page_count = result.page_count
    version.char_count = len(result.text)
    version.processed_at = utcnow()
    session.commit()
    logger.info(
        "document_extracted",
        version_id=str(version_id),
        chars=len(result.text),
        truncated=result.truncated,
    )
    return ProcessingStatus.READY.value
