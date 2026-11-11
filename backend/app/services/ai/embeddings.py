"""Embedding provider (OpenAI-compatible ``/embeddings``: Ollama, vLLM, LM Studio, OpenAI).

Synchronous ``embed`` for the indexing worker, asynchronous ``aembed`` for query embedding in
the API. Anthropic has no embeddings endpoint, so it is not an option here (settings refuse it).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

import httpx2

from app.core.config import Settings
from app.core.logging import get_logger
from app.models.vector import EMBEDDING_DIMENSIONS
from app.services.ai.config import embedding_config

logger = get_logger(__name__)

BATCH_SIZE = 32
MSG_EMBEDDING_FAILED = "สร้างดัชนีค้นหาตามความหมายไม่สำเร็จ ระบบยังค้นหาด้วยคำได้ กรุณาลองสร้างดัชนีใหม่ภายหลัง"


class EmbeddingError(Exception):
    def __init__(self, message: str = MSG_EMBEDDING_FAILED) -> None:
        super().__init__(message)
        self.message = message


class EmbeddingProvider(Protocol):
    model: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def aembed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OpenAICompatibleEmbeddings:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        api_key: str | None = None,
        transport: httpx2.BaseTransport | None = None,
        async_transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self._url = base_url.rstrip("/") + "/embeddings"
        self._timeout = timeout_seconds
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._transport = transport
        self._async_transport = async_transport

    def _parse(self, status: int, body: Any, expected: int) -> list[list[float]]:
        if status != 200:
            logger.warning("embedding_api_error", status_code=status, model=self.model)
            raise EmbeddingError()
        try:
            data = sorted(body["data"], key=lambda item: item.get("index", 0))
            vectors = [[float(x) for x in item["embedding"]] for item in data]
        except (KeyError, TypeError, ValueError):
            logger.warning("embedding_bad_response", model=self.model)
            raise EmbeddingError() from None
        if len(vectors) != expected or any(len(v) != EMBEDDING_DIMENSIONS for v in vectors):
            logger.warning(
                "embedding_dimension_mismatch",
                model=self.model,
                got=sorted({len(v) for v in vectors}),
                expected=EMBEDDING_DIMENSIONS,
            )
            raise EmbeddingError(
                f"โมเดล embedding ให้เวกเตอร์ที่ไม่ใช่ {EMBEDDING_DIMENSIONS} มิติ กรุณาตรวจการตั้งค่า"
            )
        return vectors

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        try:
            with httpx2.Client(timeout=self._timeout, transport=self._transport) as client:
                for start in range(0, len(texts), BATCH_SIZE):
                    batch = list(texts[start : start + BATCH_SIZE])
                    resp = client.post(
                        self._url, json={"model": self.model, "input": batch}, headers=self._headers
                    )
                    out += self._parse(resp.status_code, _json(resp), len(batch))
        except httpx2.HTTPError as exc:
            logger.warning("embedding_transport_error", error_type=type(exc).__name__)
            raise EmbeddingError() from None
        return out

    async def aembed(self, texts: Sequence[str]) -> list[list[float]]:
        try:
            async with httpx2.AsyncClient(
                timeout=self._timeout, transport=self._async_transport
            ) as client:
                resp = await client.post(
                    self._url,
                    json={"model": self.model, "input": list(texts)},
                    headers=self._headers,
                )
        except httpx2.HTTPError as exc:
            logger.warning("embedding_transport_error", error_type=type(exc).__name__)
            raise EmbeddingError() from None
        return self._parse(resp.status_code, _json(resp), len(texts))


def _json(resp: httpx2.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return None


def build_embedding_provider(settings: Settings) -> EmbeddingProvider | None:
    config = embedding_config(settings)
    if not config.valid or config.model is None or settings.ai_embedding_base_url is None:
        return None
    key = settings.ai_embedding_api_key
    return OpenAICompatibleEmbeddings(
        base_url=settings.ai_embedding_base_url,
        model=config.model,
        timeout_seconds=settings.ai_request_timeout_seconds,
        api_key=key.get_secret_value() if key else None,
    )
