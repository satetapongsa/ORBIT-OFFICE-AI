"""Chunking, the vector type and the embedding provider (no database, no network)."""

from __future__ import annotations

import json
from typing import Any

import httpx2
import pytest

from app.core.config import AIProvider
from app.models.vector import EMBEDDING_DIMENSIONS, from_literal, to_literal
from app.services.ai.embeddings import (
    BATCH_SIZE,
    EmbeddingError,
    OpenAICompatibleEmbeddings,
    build_embedding_provider,
)
from app.services.documents.chunking import chunk_text
from tests.conftest import make_settings, run

# --- Chunking ----------------------------------------------------------------------------


def test_short_text_is_one_chunk() -> None:
    chunks = chunk_text("  นโยบายการลา  ", size=1000, overlap=150)
    assert [(c.index, c.content, c.page) for c in chunks] == [(0, "นโยบายการลา", None)]
    assert chunk_text("", size=1000, overlap=150) == []
    assert chunk_text(" \n \f ", size=1000, overlap=150) == []


def test_chunks_respect_size_overlap_and_boundaries() -> None:
    paragraphs = [f"ข้อ {i} พนักงานต้องปฏิบัติตามระเบียบเรื่องที่ {i} อย่างเคร่งครัด" for i in range(60)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, size=300, overlap=60)
    assert len(chunks) > 5
    assert all(len(c.content) <= 300 for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    # Cuts prefer paragraph boundaries: chunks end at the end of a paragraph.
    assert all(c.content.endswith("อย่างเคร่งครัด") for c in chunks)
    # Every paragraph survives in at least one chunk (nothing is lost at a cut).
    for paragraph in paragraphs:
        assert any(paragraph in c.content for c in chunks), paragraph
    # Consecutive chunks overlap (the next chunk repeats the end of the previous one).
    assert chunks[1].content.splitlines()[0] in chunks[0].content


def test_text_without_breaks_still_splits() -> None:
    text = "ก" * 2500
    chunks = chunk_text(text, size=1000, overlap=100)
    assert [len(c.content) for c in chunks] == [1000, 1000, 700]


def test_page_numbers_from_form_feeds() -> None:
    text = "หน้าแรก " * 30 + "\f" + "หน้าที่สอง " * 30 + "\f" + "หน้าสุดท้าย"
    chunks = chunk_text(text, size=200, overlap=20)
    pages = [c.page for c in chunks]
    assert pages[0] == 1 and pages[-1] == 3
    assert pages == sorted(pages)
    assert all("\f" not in c.content for c in chunks)


@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (100, 100), (100, -1)])
def test_invalid_chunk_settings(size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_text("x", size=size, overlap=overlap)


# --- Vector literal ------------------------------------------------------------------------


def test_vector_literal_round_trip() -> None:
    assert to_literal([0.5, -1, 2.25]) == "[0.5,-1.0,2.25]"
    assert from_literal("[0.5,-1,2.25]") == [0.5, -1.0, 2.25]
    assert from_literal("[]") == []


# --- Embeddings ----------------------------------------------------------------------------


def _vectors(n: int, dims: int = EMBEDDING_DIMENSIONS) -> dict[str, Any]:
    return {"data": [{"index": i, "embedding": [0.1] * dims} for i in range(n)]}


def test_embeddings_batch_and_request_shape() -> None:
    calls: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        calls.append(
            {"url": str(request.url), "auth": request.headers.get("authorization"), **body}
        )
        return httpx2.Response(200, json=_vectors(len(body["input"])))

    embedder = OpenAICompatibleEmbeddings(
        base_url="http://llm.test/v1/",
        model="bge-m3",
        timeout_seconds=5,
        api_key="k",
        transport=httpx2.MockTransport(handler),
    )
    vectors = embedder.embed([f"t{i}" for i in range(BATCH_SIZE + 8)])
    assert len(vectors) == BATCH_SIZE + 8
    assert [len(c["input"]) for c in calls] == [BATCH_SIZE, 8]
    assert calls[0]["url"] == "http://llm.test/v1/embeddings"
    assert calls[0]["model"] == "bge-m3"
    assert calls[0]["auth"] == "Bearer k"


def test_async_embedding() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=_vectors(1))

    embedder = OpenAICompatibleEmbeddings(
        base_url="http://llm.test/v1",
        model="bge-m3",
        timeout_seconds=5,
        async_transport=httpx2.MockTransport(handler),
    )
    [vector] = run(embedder.aembed(["คำถาม"]))
    assert len(vector) == EMBEDDING_DIMENSIONS


@pytest.mark.parametrize(
    "response",
    [
        httpx2.Response(500, text="boom"),
        httpx2.Response(200, json={"unexpected": True}),
        httpx2.Response(200, json=_vectors(1, dims=768)),  # wrong model dimension
        httpx2.Response(200, json=_vectors(2)),  # wrong count
    ],
)
def test_embedding_failures(response: httpx2.Response) -> None:
    embedder = OpenAICompatibleEmbeddings(
        base_url="http://llm.test/v1",
        model="bge-m3",
        timeout_seconds=5,
        transport=httpx2.MockTransport(lambda _: response),
    )
    with pytest.raises(EmbeddingError):
        embedder.embed(["x"])


def test_embedding_connection_failure() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=request)

    embedder = OpenAICompatibleEmbeddings(
        base_url="http://llm.test/v1",
        model="bge-m3",
        timeout_seconds=5,
        transport=httpx2.MockTransport(handler),
    )
    with pytest.raises(EmbeddingError):
        embedder.embed(["x"])


def test_embedding_provider_settings() -> None:
    assert build_embedding_provider(make_settings()) is None
    built = build_embedding_provider(
        make_settings(
            ai_embedding_provider=AIProvider.OPENAI_COMPATIBLE,
            ai_embedding_model="bge-m3",
            ai_embedding_base_url="http://127.0.0.1:11434/v1",
        )
    )
    assert isinstance(built, OpenAICompatibleEmbeddings) and built.model == "bge-m3"
    # The vector column is fixed at 1024 dimensions by migration 0007.
    with pytest.raises(ValueError, match="AI_EMBEDDING_DIMENSIONS"):
        make_settings(
            ai_embedding_provider=AIProvider.OPENAI_COMPATIBLE,
            ai_embedding_model="nomic-embed-text",
            ai_embedding_base_url="http://127.0.0.1:11434/v1",
            ai_embedding_dimensions=768,
        )
