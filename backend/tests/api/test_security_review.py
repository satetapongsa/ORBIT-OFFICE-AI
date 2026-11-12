"""Phase 9 security review: route-wide authentication and CSRF sweeps, headers, readiness
visibility, per-user rate limits and the fail-closed rate limiter."""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from app.api.deps import limit_ai_summaries, limit_exports, limit_uploads
from app.core.rate_limit import RateLimiterUnavailableError, RedisRateLimiter
from app.core.security import CSRF_HEADER
from app.services import health
from tests.conftest import Factory, run

AsUser = Callable[..., TestClient]

# Endpoints that must work without a session (everything else needs one).
PUBLIC = {
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/health/live"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/password-reset/request"),
    ("POST", "/api/v1/auth/password-reset/confirm"),
}
MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def _routes(app: FastAPI) -> Iterator[tuple[str, str]]:
    """Every (method, full path) of the API, from the OpenAPI schema (no route is hidden from
    the schema in this codebase; ``test_no_route_is_hidden_from_the_schema`` keeps it so)."""
    for path, operations in app.openapi()["paths"].items():
        for method in operations:
            if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                yield method.upper(), path


def _concrete(path: str) -> str:
    # Every path parameter in this API is a UUID.
    return re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)


def test_no_route_is_hidden_from_the_schema() -> None:
    import pathlib

    sources = pathlib.Path(__file__).parents[2].joinpath("app").rglob("*.py")
    assert not [p for p in sources if "include_in_schema" in p.read_text(encoding="utf-8")]


def test_route_inventory_is_complete(api_app: FastAPI) -> None:
    routes = set(_routes(api_app))
    assert routes >= PUBLIC, "a public endpoint was renamed; update the review list"
    assert len(routes) >= 90  # sanity: the sweeps below really cover the API (95 today)


def test_every_non_public_route_requires_a_session(
    api_app: FastAPI, new_client: Callable[[], TestClient]
) -> None:
    client = new_client()
    unprotected = []
    for method, path in _routes(api_app):
        if (method, path) in PUBLIC:
            continue
        response = client.request(method, _concrete(path), json={})
        if response.status_code != 401:
            unprotected.append((method, path, response.status_code))
    assert unprotected == []


def test_every_mutating_route_requires_the_csrf_token(api_app: FastAPI, as_user: AsUser) -> None:
    client = as_user(["ADMIN"])
    client.headers.pop(CSRF_HEADER, None)
    missing = []
    for method, path in _routes(api_app):
        if method not in MUTATING or (method, path) in PUBLIC:
            continue
        response = client.request(method, _concrete(path), json={})
        if response.status_code != 403 or response.json()["error"]["code"] != "csrf_failed":
            missing.append((method, path, response.status_code))
    assert missing == []


def test_api_responses_carry_security_headers(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")
    headers = response.headers
    assert headers["Content-Security-Policy"].startswith("default-src 'none'")
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
    assert headers["Permissions-Policy"].startswith("camera=()")
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Cross-Origin-Opener-Policy"] == "same-origin"
    # Development API docs load Swagger UI from a CDN: no API CSP there.
    assert "Content-Security-Policy" not in client.get("/api/docs").headers


# --- Readiness visibility ------------------------------------------------------------------


async def _ok() -> str | None:
    return None


@pytest.fixture
def healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        health, "DEFAULT_CHECKS", {"database": _ok, "redis": _ok, "object_storage": _ok}
    )


@pytest.mark.usefixtures("healthy")
def test_public_readiness_hides_details_in_production(
    api_app: FastAPI, new_client: Callable[[], TestClient]
) -> None:
    api_app.state.settings = api_app.state.settings.model_copy(
        update={"health_details_public": False, "health_check_token": None}
    )
    body = new_client().get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["details_hidden"] is True
    assert body["components"] == [] and body["environment"] is None


@pytest.mark.usefixtures("healthy")
def test_health_token_unlocks_details(
    api_app: FastAPI, new_client: Callable[[], TestClient]
) -> None:
    from pydantic import SecretStr

    api_app.state.settings = api_app.state.settings.model_copy(
        update={"health_details_public": False, "health_check_token": SecretStr("t" * 40)}
    )
    client = new_client()
    assert client.get("/api/v1/health", headers={"X-Health-Token": "wrong"}).json()[
        "details_hidden"
    ]
    detailed = client.get("/api/v1/health", headers={"X-Health-Token": "t" * 40}).json()
    assert detailed["details_hidden"] is False
    assert {c["name"] for c in detailed["components"]} >= {"database", "redis"}


@pytest.mark.usefixtures("healthy")
def test_detailed_readiness_is_for_administrators(
    db: Factory, as_user: AsUser, new_client: Callable[[], TestClient]
) -> None:
    assert new_client().get("/api/v1/health/details").status_code == 401
    assert as_user(["EMPLOYEE"]).get("/api/v1/health/details").status_code == 403
    body = as_user(["ADMIN"]).get("/api/v1/health/details").json()
    assert body["details_hidden"] is False and body["components"]


# --- Rate limits ---------------------------------------------------------------------------


def test_upload_export_and_summary_routes_are_rate_limited() -> None:
    from app.api.v1.endpoints import analytics, documents, tasks

    def guards(router: APIRouter, method: str, path: str) -> set[Any]:
        for route in router.routes:
            if isinstance(route, APIRoute) and route.path == path and method in route.methods:
                return {d.dependency for d in route.dependencies}
        raise AssertionError(f"{method} {path} not found")

    assert limit_uploads in guards(documents.router, "POST", "/documents")
    assert limit_uploads in guards(documents.router, "POST", "/documents/{document_id}/versions")
    assert limit_uploads in guards(tasks.router, "POST", "/tasks/{task_id}/attachments")
    for path in ("/reports/overview.xlsx", "/reports/overview.pdf"):
        assert limit_exports in guards(analytics.router, "GET", path)
    assert limit_ai_summaries in guards(analytics.router, "POST", "/analytics/summary")


def test_exports_are_limited_per_user(db: Factory, api_app: FastAPI, as_user: AsUser) -> None:
    api_app.state.settings = api_app.state.settings.model_copy(update={"export_rate_limit": 2})
    alice = as_user(["MANAGER"])
    bob = as_user(["MANAGER"])
    path = "/api/v1/reports/overview.xlsx"
    assert [alice.get(path).status_code for _ in range(2)] == [200, 200]
    limited = alice.get(path)
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1
    assert bob.get(path).status_code == 200  # counted per user


class _BrokenPipeline:
    async def __aenter__(self) -> _BrokenPipeline:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def __getattr__(self, name: str) -> Callable[..., Any]:
        async def fail(*_: object, **__: object) -> None:
            raise RedisConnectionError("redis down")

        if name == "execute":
            return fail
        return lambda *a, **k: None


class _BrokenRedis:
    def pipeline(self, transaction: bool = True) -> _BrokenPipeline:
        return _BrokenPipeline()


def test_limiter_fails_closed_when_configured() -> None:
    closed = RedisRateLimiter(_BrokenRedis(), fail_open=False)  # type: ignore[arg-type]
    with pytest.raises(RateLimiterUnavailableError):
        run(closed.hit("login:x", limit=5, window_seconds=60))
    opened = RedisRateLimiter(_BrokenRedis(), fail_open=True)  # type: ignore[arg-type]
    assert run(opened.hit("login:x", limit=5, window_seconds=60)).allowed is True


def test_login_is_refused_while_the_limiter_is_down(
    db: Factory, api_app: FastAPI, new_client: Callable[[], TestClient]
) -> None:
    db.user("alice@example.com")
    api_app.state.rate_limiter = RedisRateLimiter(_BrokenRedis(), fail_open=False)  # type: ignore[arg-type]
    response = new_client().post(
        "/api/v1/auth/login", json={"email": "alice@example.com", "password": "whatever-1234"}
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "rate_limiter_unavailable"
