from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

import anyio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import health


async def _ok() -> str | None:
    return None


async def _boom() -> str | None:
    raise ConnectionRefusedError("secret-host:5432 password=hunter2")


async def _slow() -> str | None:
    await asyncio.sleep(5)
    return None


async def _missing_vector() -> str | None:
    raise health.DependencyCheckError("pgvector extension missing")


@pytest.fixture
def all_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        health, "DEFAULT_CHECKS", {"database": _ok, "redis": _ok, "object_storage": _ok}
    )


def test_liveness_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "ORBIT OFFICE AI"


def test_liveness_sets_request_id_and_security_headers(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")
    assert len(response.headers["X-Request-ID"]) >= 8
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


@pytest.mark.usefixtures("all_ok")
def test_readiness_ok_when_all_required_components_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    names = {c["name"]: c for c in body["components"]}
    assert set(names) == {"database", "redis", "object_storage", "ai_chat", "ai_embedding"}
    assert names["ai_chat"]["status"] == "not_configured"
    assert names["ai_chat"]["required"] is False


def test_readiness_503_and_hides_error_details(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        health, "DEFAULT_CHECKS", {"database": _boom, "redis": _ok, "object_storage": _ok}
    )
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    database = next(c for c in response.json()["components"] if c["name"] == "database")
    assert database["status"] == "error"
    assert database["detail"] == "unavailable"
    assert "hunter2" not in response.text
    assert "secret-host" not in response.text


def test_readiness_reports_known_dependency_problem(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        health,
        "DEFAULT_CHECKS",
        {"database": _missing_vector, "redis": _ok, "object_storage": _ok},
    )
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    database = next(c for c in response.json()["components"] if c["name"] == "database")
    assert database["detail"] == "pgvector extension missing"


def test_readiness_check_timeout(
    app_factory: Callable[..., FastAPI], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        health, "DEFAULT_CHECKS", {"database": _ok, "redis": _slow, "object_storage": _ok}
    )
    client = TestClient(app_factory(health_check_timeout_seconds=0.05))
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    redis = next(c for c in response.json()["components"] if c["name"] == "redis")
    assert redis["detail"] == "timed out"


async def _blocking_thread() -> str | None:
    # Mimics boto3: a blocking call in a worker thread must not defeat the timeout.
    await anyio.to_thread.run_sync(time.sleep, 2, abandon_on_cancel=True)
    return None


def test_readiness_timeout_applies_to_blocking_thread_checks(
    app_factory: Callable[..., FastAPI], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        health,
        "DEFAULT_CHECKS",
        {"database": _ok, "redis": _ok, "object_storage": _blocking_thread},
    )
    client = TestClient(app_factory(health_check_timeout_seconds=0.05))
    started = time.perf_counter()
    response = client.get("/api/v1/health")
    assert time.perf_counter() - started < 1.5
    storage = next(c for c in response.json()["components"] if c["name"] == "object_storage")
    assert storage["detail"] == "timed out"


@pytest.mark.usefixtures("all_ok")
def test_ai_configured_is_reported_without_contacting_provider(
    app_factory: Callable[..., FastAPI],
) -> None:
    client = TestClient(
        app_factory(
            ai_chat_provider="openai_compatible",
            ai_chat_model="qwen3:8b",
            ai_chat_base_url="http://localhost:11434/v1",
        )
    )
    body = client.get("/api/v1/health").json()
    chat = next(c for c in body["components"] if c["name"] == "ai_chat")
    assert chat["status"] == "configured"
    assert "connectivity not checked" in chat["detail"]
    # AI is optional: readiness stays OK.
    assert body["status"] == "ok"


@pytest.mark.usefixtures("all_ok")
def test_ai_misconfiguration_is_reported(app_factory: Callable[..., FastAPI]) -> None:
    client = TestClient(app_factory(ai_chat_provider="anthropic"))
    body = client.get("/api/v1/health").json()
    chat = next(c for c in body["components"] if c["name"] == "ai_chat")
    assert chat["status"] == "error"
    assert "AI_CHAT_MODEL is required" in chat["detail"]
    assert "AI_CHAT_API_KEY is required" in chat["detail"]
