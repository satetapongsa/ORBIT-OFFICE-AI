"""API behind a separately hosted front end (ADR-055): the shared proxy secret, the visitor
IP reported by the proxy, and no shared caching of API responses."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from app.core.middleware import TrustedProxyMiddleware
from tests.conftest import BACKEND_OPTIONS

SECRET = "s" * 40
HEADER = "X-Orbit-Proxy-Secret"


def _client(app_factory: Callable[..., FastAPI], **overrides: Any) -> TestClient:
    app = app_factory(**overrides)
    return TestClient(app, raise_server_exceptions=False, backend_options=BACKEND_OPTIONS)


def test_requests_without_the_secret_are_refused(app_factory: Callable[..., FastAPI]) -> None:
    client = _client(app_factory, proxy_shared_secret=SECRET)
    for headers in ({}, {HEADER: "wrong"}, {HEADER: SECRET[:-1]}):
        response = client.get("/api/v1/auth/me", headers=headers)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "proxy_required"
        # Refusals still carry the usual security headers.
        assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_requests_with_the_secret_reach_the_api(app_factory: Callable[..., FastAPI]) -> None:
    client = _client(app_factory, proxy_shared_secret=SECRET)
    response = client.get("/api/v1/auth/me", headers={HEADER: SECRET})
    assert response.status_code == 401  # past the proxy check, now asking for a session


def test_liveness_probe_needs_no_secret(app_factory: Callable[..., FastAPI]) -> None:
    client = _client(app_factory, proxy_shared_secret=SECRET)
    assert client.get("/api/v1/health/live").status_code == 200


def test_without_a_secret_configured_nothing_changes(app_factory: Callable[..., FastAPI]) -> None:
    client = _client(app_factory, proxy_shared_secret="")
    assert client.get("/api/v1/auth/me").status_code == 401


def _echo_app() -> TrustedProxyMiddleware:
    async def echo(scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive)
        body = {
            "client": request.client.host if request.client else None,
            "headers": sorted(request.headers.keys()),
        }
        await JSONResponse(body)(scope, receive, send)

    return TrustedProxyMiddleware(echo, secret=SECRET)


def test_visitor_ip_comes_from_the_proxy_and_the_secret_is_dropped() -> None:
    client = TestClient(_echo_app(), backend_options=BACKEND_OPTIONS)
    body = client.get(
        "/api/v1/anything",
        headers={HEADER: SECRET, "X-Vercel-Forwarded-For": "203.0.113.7, 10.0.0.1"},
    ).json()
    assert body["client"] == "203.0.113.7"
    assert "x-orbit-proxy-secret" not in body["headers"]


def test_an_invalid_visitor_ip_keeps_the_connection_address() -> None:
    client = TestClient(_echo_app(), backend_options=BACKEND_OPTIONS)
    body = client.get(
        "/api/v1/anything", headers={HEADER: SECRET, "X-Vercel-Forwarded-For": "not-an-ip"}
    ).json()
    assert body["client"] == "testclient"


def test_api_responses_are_never_stored_by_shared_caches(client: TestClient) -> None:
    assert client.get("/api/v1/health/live").headers["Cache-Control"] == "no-store"
    assert client.get("/api/v1/auth/me").headers["Cache-Control"] == "no-store"
