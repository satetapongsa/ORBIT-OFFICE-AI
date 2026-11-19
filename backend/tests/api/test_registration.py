"""Self-service sign-up with e-mail confirmation (ADR-057)."""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.rate_limit import InMemoryRateLimiter
from app.main import create_app
from tests.conftest import (
    BACKEND_OPTIONS,
    CapturingNotifier,
    Factory,
    login,
    make_settings,
    sync_csrf,
)

PASSWORD = "Fresh-Signup-Pass-2026"
FORM = {
    "email": "new.person@orbit.example.com",
    "first_name": "สมชาย",
    "last_name": "ใจดี",
    "password": PASSWORD,
}


@pytest.fixture
def reg_app(db: Factory) -> FastAPI:
    app = create_app(
        make_settings(self_registration_enabled=True, self_registration_domains="orbit.example.com")
    )
    app.state.rate_limiter = InMemoryRateLimiter()
    app.state.reset_notifier = CapturingNotifier()
    return app


@pytest.fixture
def anon(reg_app: FastAPI) -> TestClient:
    with TestClient(reg_app, raise_server_exceptions=False, backend_options=BACKEND_OPTIONS) as c:
        yield c  # type: ignore[misc]


def _token(app: FastAPI, index: int = -1) -> str:
    url = app.state.reset_notifier.verifications[index]["verify_url"]
    return parse_qs(urlparse(url).query)["token"][0]


def test_settings_require_domains_when_enabled() -> None:
    with pytest.raises(ValueError, match="SELF_REGISTRATION_DOMAINS"):
        make_settings(self_registration_enabled=True)
    s: Settings = make_settings(
        self_registration_enabled=True, self_registration_domains=" @Orbit.Example.COM , b.co "
    )
    assert s.self_registration_domains == ["orbit.example.com", "b.co"]


def test_disabled_by_default(db: Factory, new_client: Callable[[], TestClient]) -> None:
    c = new_client()
    assert c.get("/api/v1/auth/registration").json() == {"enabled": False, "allowed_domains": []}
    r = c.post("/api/v1/auth/register", json=FORM)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "registration_disabled"
    assert c.post("/api/v1/auth/verify-email", json={"token": "x" * 43}).status_code == 403


def test_full_sign_up_flow(db: Factory, reg_app: FastAPI, anon: TestClient) -> None:
    assert anon.get("/api/v1/auth/registration").json() == {
        "enabled": True,
        "allowed_domains": ["orbit.example.com"],
    }
    r = anon.post("/api/v1/auth/register", json={**FORM, "email": "New.Person@ORBIT.example.com"})
    assert r.status_code == 202, r.text
    # Not an account yet: cannot sign in before confirming.
    assert db.scalar("SELECT count(*) FROM users WHERE email = 'new.person@orbit.example.com'") == 0
    bad = anon.post("/api/v1/auth/login", json={"email": FORM["email"], "password": PASSWORD})
    assert bad.status_code == 401
    token = _token(reg_app)
    # The token is stored only as a hash.
    assert (
        db.scalar("SELECT count(*) FROM pending_registrations WHERE token_hash = :t", t=token) == 0
    )

    done = anon.post("/api/v1/auth/verify-email", json={"token": token})
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["user"]["email"] == "new.person@orbit.example.com"
    assert body["user"]["display_name"] == "สมชาย ใจดี"
    assert [r["code"] for r in body["user"]["roles"]] == ["EMPLOYEE"]
    assert "users:create" not in body["permissions"]
    sync_csrf(anon)
    assert anon.get("/api/v1/auth/me").status_code == 200  # signed in by the link
    assert db.scalar("SELECT count(*) FROM pending_registrations") == 0
    assert db.scalar("SELECT count(*) FROM audit_logs WHERE action = 'auth.registered'") == 1

    again = anon.post("/api/v1/auth/verify-email", json={"token": token})
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "invalid_verification_token"

    with TestClient(reg_app, raise_server_exceptions=False, backend_options=BACKEND_OPTIONS) as c:
        login(c, FORM["email"], PASSWORD)


def test_rejects_foreign_domain_and_weak_password(reg_app: FastAPI, anon: TestClient) -> None:
    r = anon.post("/api/v1/auth/register", json={**FORM, "email": "someone@gmail.com"})
    assert r.status_code == 422
    assert r.json()["error"]["details"][0]["field"] == "email"
    weak = anon.post("/api/v1/auth/register", json={**FORM, "password": "short"})
    assert weak.status_code == 422
    assert reg_app.state.reset_notifier.verifications == []


def test_existing_account_gets_same_answer_and_no_mail(
    db: Factory, reg_app: FastAPI, anon: TestClient
) -> None:
    db.user("taken@orbit.example.com")
    existing = anon.post("/api/v1/auth/register", json={**FORM, "email": "taken@orbit.example.com"})
    fresh = anon.post("/api/v1/auth/register", json=FORM)
    assert existing.status_code == fresh.status_code == 202
    assert existing.json() == fresh.json()  # no account enumeration
    assert [v["email"] for v in reg_app.state.reset_notifier.verifications] == [FORM["email"]]


def test_registering_again_replaces_the_pending_link(
    db: Factory, reg_app: FastAPI, anon: TestClient
) -> None:
    anon.post("/api/v1/auth/register", json=FORM)
    first = _token(reg_app)
    anon.post("/api/v1/auth/register", json={**FORM, "first_name": "ตัวจริง"})
    second = _token(reg_app)
    assert db.scalar("SELECT count(*) FROM pending_registrations") == 1
    assert anon.post("/api/v1/auth/verify-email", json={"token": first}).status_code == 400
    ok = anon.post("/api/v1/auth/verify-email", json={"token": second})
    assert ok.status_code == 200
    assert ok.json()["user"]["first_name"] == "ตัวจริง"


def test_expired_link_and_account_created_meanwhile(
    db: Factory, reg_app: FastAPI, anon: TestClient
) -> None:
    anon.post("/api/v1/auth/register", json=FORM)
    token = _token(reg_app)
    with db.engine.begin() as conn:
        from sqlalchemy import text

        conn.execute(text("UPDATE pending_registrations SET expires_at = now() - interval '1 m'"))
    assert anon.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 400

    anon.post("/api/v1/auth/register", json=FORM)
    token = _token(reg_app)
    db.user(FORM["email"])  # HR created the account before the link was used
    assert anon.post("/api/v1/auth/verify-email", json={"token": token}).status_code == 400
    assert db.scalar("SELECT count(*) FROM pending_registrations") == 0


def test_rate_limited(reg_app: FastAPI, anon: TestClient) -> None:
    codes = [anon.post("/api/v1/auth/register", json=FORM).status_code for _ in range(6)]
    assert codes[:5] == [202] * 5
    assert codes[5] == 429
