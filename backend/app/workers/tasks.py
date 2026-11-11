"""Background tasks."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from celery.exceptions import SoftTimeLimitExceeded

from app.core.db import sync_session_scope
from app.core.logging import get_logger
from app.core.storage import get_storage
from app.workers.celery_app import celery_app

logger = get_logger(__name__)

EXTRACT_SOFT_LIMIT_SECONDS = 180


@celery_app.task(name="system.ping")
def ping() -> dict[str, str]:
    """Round-trip check used to verify broker → worker → result backend wiring."""
    return {"status": "ok", "at": datetime.now(UTC).isoformat()}


@celery_app.task(
    name="documents.extract_text",
    soft_time_limit=EXTRACT_SOFT_LIMIT_SECONDS,
    time_limit=EXTRACT_SOFT_LIMIT_SECONDS + 30,
)
def extract_document_text(version_id: str, force: bool = False) -> str:
    from app.services.documents.processing import (
        GENERIC_FAILURE,
        TIMEOUT_FAILURE,
        mark_failed,
        process_version,
    )

    vid = uuid.UUID(version_id)
    try:
        with sync_session_scope() as session:
            status = process_version(session, get_storage(), vid, force=force)
        if status == "READY":
            # Index right away; a failure here never undoes the extracted text.
            _index(vid, force=True)
        return status
    except SoftTimeLimitExceeded:
        message = TIMEOUT_FAILURE
    except Exception:
        logger.exception("document_processing_error", version_id=version_id)
        message = GENERIC_FAILURE
    with sync_session_scope() as session:
        mark_failed(session, vid, message)
    return "FAILED"


def _index(version_id: uuid.UUID, *, force: bool) -> str:
    from app.core.config import get_settings
    from app.services.ai.embeddings import build_embedding_provider
    from app.services.documents.indexing import index_version

    settings = get_settings()
    try:
        with sync_session_scope() as session:
            return index_version(
                session, settings, build_embedding_provider(settings), version_id, force=force
            )
    except Exception:
        logger.exception("document_indexing_error", version_id=str(version_id))
        return "FAILED"


@celery_app.task(
    name="documents.index_version",
    soft_time_limit=EXTRACT_SOFT_LIMIT_SECONDS,
    time_limit=EXTRACT_SOFT_LIMIT_SECONDS + 30,
)
def index_document_version(version_id: str, force: bool = False) -> str:
    return _index(uuid.UUID(version_id), force=force)
