"""Passage retrieval for RAG and content search.

**Permission filtering happens here, in SQL, before any text leaves the database**
(docs/SECURITY.md §5): every query joins ``documents`` with ``accessible_documents_condition``
and only reads chunks of each document's current, processed version. Nothing is fetched first
and filtered later, so an unauthorised passage can never reach the model or the browser.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.principal import CurrentUser
from app.models.document import Document, DocumentChunk, DocumentVersion, ProcessingStatus
from app.repositories.document_access import accessible_documents_condition

KEYWORD_MIN_SIMILARITY = 0.3


@dataclass(frozen=True, slots=True)
class Hit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    version_id: uuid.UUID
    version_number: int
    title: str
    category: str
    page: int | None
    content: str
    score: float


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _base(user: CurrentUser, score: Any) -> Any:
    return (
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            DocumentChunk.document_version_id,
            DocumentVersion.version_number,
            Document.title,
            Document.category,
            DocumentChunk.page_number,
            DocumentChunk.content,
            score.label("score"),
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .join(DocumentVersion, DocumentVersion.id == DocumentChunk.document_version_id)
        .where(
            accessible_documents_condition(user),
            DocumentChunk.document_version_id == Document.current_version_id,
            DocumentVersion.processing_status == ProcessingStatus.READY.value,
        )
    )


def _hits(rows: Any) -> list[Hit]:
    return [
        Hit(
            chunk_id=r[0],
            document_id=r[1],
            version_id=r[2],
            version_number=r[3],
            title=r[4],
            category=r[5],
            page=r[6],
            content=r[7],
            score=float(r[8]),
        )
        for r in rows
    ]


async def semantic_search(
    session: AsyncSession,
    user: CurrentUser,
    vector: list[float],
    *,
    model: str,
    limit: int,
) -> list[Hit]:
    """Nearest passages by cosine similarity among chunks embedded with ``model``."""
    # pgvector ≥ 0.8: keep scanning the HNSW index until enough rows pass the ACL filter.
    await session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    await session.execute(text("SET LOCAL hnsw.ef_search = 100"))
    distance = DocumentChunk.embedding.cosine_distance(vector)
    stmt = (
        _base(user, 1 - distance)
        .where(DocumentChunk.embedding_model == model, DocumentChunk.embedding.is_not(None))
        .order_by(distance)
        .limit(limit)
    )
    hits = _hits(await session.execute(stmt))
    # relaxed_order may return rows slightly out of order.
    return sorted(hits, key=lambda h: h.score, reverse=True)


async def keyword_search(
    session: AsyncSession, user: CurrentUser, query: str, *, limit: int
) -> list[Hit]:
    """Trigram word similarity (works for Thai, which has no spaces) or a literal match."""
    similarity = func.word_similarity(query, DocumentChunk.content)
    pattern = f"%{_escape_like(query)}%"
    stmt = (
        _base(user, similarity)
        .where(
            or_(
                similarity >= KEYWORD_MIN_SIMILARITY,
                DocumentChunk.content.ilike(pattern, escape="\\"),
            )
        )
        .order_by(similarity.desc(), DocumentChunk.id)
        .limit(limit)
    )
    return _hits(await session.execute(stmt))
