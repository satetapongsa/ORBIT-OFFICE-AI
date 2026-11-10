from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.core.errors import NotFoundError


class _Payload(BaseModel):
    title: str = Field(min_length=3)


def _app_with_test_routes(app_factory: Callable[..., FastAPI]) -> FastAPI:
    app = app_factory()

    @app.get("/api/v1/_test/not-found")
    async def not_found() -> None:
        raise NotFoundError()

    @app.post("/api/v1/_test/validate")
    async def validate(payload: _Payload) -> _Payload:
        return payload

    @app.get("/api/v1/_test/crash")
    async def crash() -> None:
        raise RuntimeError("database password is hunter2")

    return app


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["request_id"] == response.headers["X-Request-ID"]


def test_app_error_envelope(app_factory: Callable[..., FastAPI]) -> None:
    client = TestClient(_app_with_test_routes(app_factory))
    response = client.get("/api/v1/_test/not-found")
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "ไม่พบข้อมูลที่ต้องการ"


def test_validation_error_envelope(app_factory: Callable[..., FastAPI]) -> None:
    client = TestClient(_app_with_test_routes(app_factory))
    response = client.post("/api/v1/_test/validate", json={"title": "x"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["field"] == "title"


def test_unhandled_error_is_generic_and_correlated(app_factory: Callable[..., FastAPI]) -> None:
    client = TestClient(_app_with_test_routes(app_factory), raise_server_exceptions=False)
    response = client.get("/api/v1/_test/crash", headers={"X-Request-ID": "trace-abc-12345"})
    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "internal_error"
    assert error["request_id"] == "trace-abc-12345"
    assert response.headers["X-Request-ID"] == "trace-abc-12345"
    assert "hunter2" not in response.text
    assert "Traceback" not in response.text


def test_malformed_client_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/api/v1/health/live", headers={"X-Request-ID": "bad id\r\n<script>"})
    assert response.headers["X-Request-ID"] != "bad id\r\n<script>"
    assert response.headers["X-Request-ID"].isalnum()
