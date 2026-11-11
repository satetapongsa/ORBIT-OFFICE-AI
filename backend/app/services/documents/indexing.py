"""Search index for one document version (synchronous; runs in the worker after extraction).

States: PENDING → INDEXING → READY | FAILED | SKIPPED.

* Chunks are always stored, so keyword search works without an embedding provider.
* With an embedding provider each chunk also gets a vector; a provider failure leaves the
  chunks (keyword search) and marks the version FAILED so it can be re-indexed.
* Only the current version is searchable (enforced at query time); chunks of older versions
  of the same document are removed when a newer version is indexed.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.security import utcnow
from app.models.document import (
    Document,
    DocumentChunk,
    DocumentVersion,
    DocumentVersionText,
    IndexStatus,
    ProcessingStatus,
)
from app.services.ai.embeddings import EmbeddingError, EmbeddingProvider
from app.services.documents.chunking import chunk_text

logger = get_logger(__name__)

NO_TEXT = "ไม่มีข้อความให้สร้างดัชนี (อาจเป็นเอกสารสแกน)"


def _load(session: Session, version_id: uuid.UUID) -> tuple[DocumentVersion, Document] | None:
    row = session.execute(
        select(DocumentVersion, Document)
        .join(Document, Document.id == DocumentVersion.document_id)
        .where(DocumentVersion.id == version_id)
        .with_for_update(of=DocumentVersion)
    ).first()
    return (row[0], row[1]) if row else None


def index_version(
    session: Session,
    settings: Settings,
    embedder: EmbeddingProvider | None,
    version_id: uuid.UUID,
    *,
    force: bool = False,
) -> str:
    """Build (or rebuild) the chunks of a version. Returns the final index status."""
    loaded = _load(session, version_id)
    if loaded is None:
        return "MISSING"
    version, document = loaded
    if document.deleted_at is not None or version.processing_status != ProcessingStatus.READY.value:
        session.rollback()
        return version.index_status
    if version.index_status == IndexStatus.READY.value and not force:
        session.rollback()
        return IndexStatus.READY.value

    text = session.scalar(
        select(DocumentVersionText.content).where(
            DocumentVersionText.document_version_id == version_id
        )
    )
    chunks = chunk_text(
        text or "", size=settings.rag_chunk_size, overlap=settings.rag_chunk_overlap
    )
    # Older versions of this document are never searched again.
    session.execute(
        delete(DocumentChunk).where(
            DocumentChunk.document_id == document.id,
            DocumentChunk.document_version_id != version_id,
        )
    )
    session.execute(delete(DocumentChunk).where(DocumentChunk.document_version_id == version_id))
    if not chunks:
        version.index_status = IndexStatus.SKIPPED.value
        version.index_error = NO_TEXT
        version.chunk_count = 0
        version.indexed_at = utcnow()
        session.commit()
        return IndexStatus.SKIPPED.value

    version.index_status = IndexStatus.INDEXING.value
    version.index_error = None
    session.commit()  # make INDEXING visible; embedding can take a while

    vectors: list[list[float]] | None = None
    error: str | None = None
    if embedder is not None:
        try:
            vectors = embedder.embed([c.content for c in chunks])
        except EmbeddingError as exc:
            error = exc.message

    loaded = _load(session, version_id)
    if loaded is None:
        return "MISSING"
    version, document = loaded
    for i, chunk in enumerate(chunks):
        session.add(
            DocumentChunk(
                document_id=document.id,
                document_version_id=version_id,
                chunk_index=chunk.index,
                page_number=chunk.page,
                content=chunk.content,
                char_count=len(chunk.content),
                embedding=vectors[i] if vectors is not None else None,
                embedding_model=embedder.model if vectors is not None and embedder else None,
            )
        )
    version.index_status = IndexStatus.FAILED.value if error else IndexStatus.READY.value
    version.index_error = error
    version.chunk_count = len(chunks)
    version.indexed_at = utcnow()
    session.commit()
    logger.info(
        "document_indexed",
        version_id=str(version_id),
        chunks=len(chunks),
        embedded=vectors is not None,
        status=version.index_status,
    )
    return version.index_status


def versions_to_index(session: Session, *, include_ready: bool) -> list[uuid.UUID]:
    """Current versions of live documents that need (re)indexing."""
    stmt = (
        select(DocumentVersion.id)
        .join(Document, Document.current_version_id == DocumentVersion.id)
        .where(
            Document.deleted_at.is_(None),
            DocumentVersion.processing_status == ProcessingStatus.READY.value,
        )
    )
    if not include_ready:
        stmt = stmt.where(DocumentVersion.index_status != IndexStatus.READY.value)
    return list(session.scalars(stmt).all())
