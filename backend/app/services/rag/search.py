"""Retrieval over the documents a user may read (Phase 7).

* ``hybrid``  — semantic (pgvector) and keyword (pg_trgm) results fused by reciprocal rank;
  used when an embedding provider is configured.
* ``keyword`` — without an embedding provider, or when embedding the query fails.

Both paths go through ``app.repositories.rag``, which applies the document ACL in SQL.
Results are passages of untrusted document text.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.principal import CurrentUser
from app.repositories import rag as rag_repo
from app.repositories.rag import Hit
from app.services.ai.embeddings import EmbeddingError, EmbeddingProvider

logger = get_logger(__name__)

SearchMode = Literal["hybrid", "keyword"]
# Passages less similar than this are not offered as evidence.
SEMANTIC_MIN_SCORE = 0.25
RRF_K = 60
CANDIDATES = 30


@dataclass(frozen=True, slots=True)
class SearchResult:
    mode: SearchMode
    hits: list[Hit]
    degraded: bool = False  # embeddings configured but unavailable for this query


def _fuse(*rankings: list[Hit], limit: int) -> list[Hit]:
    """Reciprocal rank fusion; each hit keeps its best original score for display."""
    scores: dict[uuid.UUID, float] = {}
    best: dict[uuid.UUID, Hit] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)
            if hit.chunk_id not in best or hit.score > best[hit.chunk_id].score:
                best[hit.chunk_id] = hit
    order = sorted(scores, key=lambda cid: scores[cid], reverse=True)
    return [best[cid] for cid in order[:limit]]


async def search(
    session: AsyncSession,
    user: CurrentUser,
    query: str,
    *,
    limit: int,
    embedder: EmbeddingProvider | None,
) -> SearchResult:
    query = query.strip()
    if not query:
        return SearchResult(mode="keyword", hits=[])
    keyword = await rag_repo.keyword_search(session, user, query, limit=CANDIDATES)
    if embedder is None:
        return SearchResult(mode="keyword", hits=keyword[:limit])
    try:
        [vector] = await embedder.aembed([query])
    except EmbeddingError:
        logger.warning("rag_query_embedding_failed")
        return SearchResult(mode="keyword", hits=keyword[:limit], degraded=True)
    semantic = [
        h
        for h in await rag_repo.semantic_search(
            session, user, vector, model=embedder.model, limit=CANDIDATES
        )
        if h.score >= SEMANTIC_MIN_SCORE
    ]
    return SearchResult(mode="hybrid", hits=_fuse(semantic, keyword, limit=limit))


def best_per_document(hits: list[Hit], *, limit: int) -> list[Hit]:
    """One passage per document, in ranking order (for the content search page)."""
    seen: set[uuid.UUID] = set()
    out: list[Hit] = []
    for hit in hits:
        if hit.document_id not in seen:
            seen.add(hit.document_id)
            out.append(hit)
        if len(out) == limit:
            break
    return out
