"""Authentication flows against the real test database."""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.security import ACCESS_COOKIE, CSRF_COOKIE, CSRF_HEADER, REFRESH_COOKIE
from tests.conftest import TEST_PASSWORD, Factory, login, make_settings, sync_csrf

NewClient = Callable[[], TestClient]


def _set_cookie_headers(response) -> list[str]:  # type: ignore[no-untyped-def]
    return response.headers.get_list("set-cookie")


def test_login_sets_secure_session_cookies_and_returns_permissions(
    db: Factory, new_client: NewClient
) -> None:
    db.user("emp@example.com", ["EMPLOYEE"])
    client = new_client()
    response = client.post(
        "/api/v1/auth/login", json={"email": "EMP@example.com", "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["email"] == "emp@example.com"
    assert "documents:read" in body["permissions"]
    assert "users:read" not in body["permissions"]

    cookies = {c.split("=", 1)[0]: c for c in _set_cookie_headers(response)}
    assert "HttpOnly" in cookies[ACCESS_COOKIE] and "Path=/api" in cookies[ACCESS_COOKIE]
    assert "HttpOnly" in cookies[REFRESH_COOKIE] and "Path=/api/v1/auth" in cookies[REFRESH_COOKIE]
    assert "HttpOnly" not in cookies[CSRF_COOKIE]  # readable by the frontend
    assert all("SameSite=lax" in c for c in cookies.values())
    assert db.scalar("SELECT count(*) FROM audit_logs WHERE action = 'auth.login'") == 1


def test_wrong_password_and_unknown_email_get_the_same_generic_error(
    db: Factory, new_client: NewClient
) -> None:
    db.user("emp@example.com")
    client = new_client()
    bad = client.post("/api/v1/auth/login", json={"email": "emp@example.com", "password": "nope"})
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "ghost@example.com", "password": "nope"}
    )
    assert bad.status_code == unknown.status_code == 401
    assert bad.json()["error"]["message"] == unknown.json()["error"]["message"]
    assert db.scalar("SELECT count(*) FROM audit_logs WHERE action = 'auth.login_failed'") == 2
    # The password is never written to the audit log.
    assert db.scalar("SELECT count(*) FROM audit_logs WHERE metadata::text ILIKE '%nope%'") == 0


def test_inactive_user_cannot_log_in(db: Factory, new_client: NewClient) -> None:
    db.user("gone@example.com", active=False)
    response = new_client().post(
        "/api/v1/auth/login", json={"email": "gone@example.com", "password": TEST_PASSWORD}
    )
    assert response.status_code == 401


def test_protected_endpoints_reject_unauthenticated_requests(
    db: Factory, new_client: NewClient
) -> None:
    client = new_client()
    for method, path in [
        ("GET", "/api/v1/auth/me"),
        ("GET", "/api/v1/users"),
        ("GET", "/api/v1/departments"),
        ("GET", "/api/v1/roles"),
        ("GET", "/api/v1/permissions"),
        ("GET", "/api/v1/audit-logs"),
        ("POST", "/api/v1/departments"),
    ]:
        response = client.request(method, path, json={})
        assert response.status_code == 401, (method, path, response.text)
        assert response.json()["error"]["code"] == "unauthenticated"


def test_bearer_token_and_cookie_both_authenticate(db: Factory, new_client: NewClient) -> None:
    db.user("emp@example.com")
    client = login(new_client(), "emp@example.com")
    assert client.get("/api/v1/auth/me").status_code == 200

    token = client.cookies.get(ACCESS_COOKIE)
    other = new_client()
    me = other.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "emp@example.com"


def test_tampered_access_token_is_rejected(db: Factory, new_client: NewClient) -> None:
    db.user("emp@example.com")
    client = login(new_client(), "emp@example.com")
    token = client.cookies.get(ACCESS_COOKIE) or ""
    forged = token[:-3] + ("aaa" if not token.endswith("aaa") else "bbb")
    response = new_client().get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_cookie_requests_that_change_state_require_csrf_token(
    db: Factory, new_client: NewClient
) -> None:
    db.user("admin@example.com", ["ADMIN"])
    client = login(new_client(), "admin@example.com")
    client.headers.pop(CSRF_HEADER)
    missing = client.post("/api/v1/departments", json={"code": "OPS", "name": "Ops"})
    assert missing.status_code == 403
    assert missing.json()["error"]["code"] == "csrf_failed"

    client.headers[CSRF_HEADER] = "wrong-token"
    assert (
        client.post("/api/v1/departments", json={"code": "OPS", "name": "Ops"}).status_code == 403
    )

    sync_csrf(client)
    assert (
        client.post("/api/v1/departments", json={"code": "OPS", "name": "Ops"}).status_code == 201
    )
    # Safe methods do not need the header.
    client.headers.pop(CSRF_HEADER)
    assert client.get("/api/v1/departments").status_code == 200


def test_refresh_rotates_tokens(db: Factory, new_client: NewClient) -> None:
    db.user("emp@example.com")
    client = login(new_client(), "emp@example.com")
    old_refresh = client.cookies.get(REFRESH_COOKIE)
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 200, response.text
    assert client.cookies.get(REFRESH_COOKIE) != old_refresh
    sync_csrf(client)
    assert client.get("/api/v1/auth/me").status_code == 200


def test_refresh_without_session_is_unauthenticated(db: Factory, new_client: NewClient) -> None:
    response = new_client().post("/api/v1/auth/refresh")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_refresh_requires_csrf(db: Factory, new_client: NewClient) -> None:
    db.user("emp@example.com")
    client = login(new_client(), "emp@example.com")
    client.headers.pop(CSRF_HEADER)
    assert client.post("/api/v1/auth/refresh").status_code == 403


def test_reused_refresh_token_revokes_the_whole_session(
    db: Factory, new_client: NewClient, api_app: FastAPI
) -> None:
    api_app.state.settings = make_settings(refresh_reuse_grace_seconds=0)
    db.user("emp@example.com")
    victim = login(new_client(), "emp@example.com")
    stolen_refresh = victim.cookies.get(REFRESH_COOKIE)
    csrf = victim.cookies.get(CSRF_COOKIE)

    assert victim.post("/api/v1/auth/refresh").status_code == 200  # legitimate rotation
    sync_csrf(victim)

    attacker = new_client()
    attacker.cookies.set(REFRESH_COOKIE, stolen_refresh or "", path="/api/v1/auth")
    attacker.cookies.set(CSRF_COOKIE, csrf or "", path="/")
    attacker.headers[CSRF_HEADER] = csrf or ""
    reuse = attacker.post("/api/v1/auth/refresh")
    assert reuse.status_code == 401
    assert any(c.startswith(f"{REFRESH_COOKIE}=") for c in _set_cookie_headers(reuse))  # cleared

    # The victim's current session (same family) is revoked as well.
    assert victim.get("/api/v1/auth/me").status_code == 401
    assert (
        db.scalar("SELECT count(*) FROM audit_logs WHERE action = 'auth.refresh_reuse_detected'")
        == 1
    )


def test_parallel_refresh_within_grace_window_does_not_log_out(
    db: Factory, new_client: NewClient
) -> None:
    db.user("emp@example.com")
    client = login(new_client(), "emp@example.com")
    first_refresh = client.cookies.get(REFRESH_COOKIE)
    assert client.post("/api/v1/auth/refresh").status_code == 200
    sync_csrf(client)

    other_tab = new_client()
    other_tab.cookies.set(REFRESH_COOKIE, first_refresh or "", path="/api/v1/auth")
    other_tab.cookies.set(CSRF_COOKIE, client.cookies.get(CSRF_COOKIE) or "", path="/")
    sync_csrf(other_tab)
    conflict = other_tab.post("/api/v1/auth/refresh")
    assert conflict.status_code == 401
    assert conflict.json()["error"]["code"] == "session_refresh_conflict"
    assert client.get("/api/v1/auth/me").status_code == 200  # session still valid


def test_logout_revokes_session_immediately(db: Factory, new_client: NewClient) -> None:
    db.user("emp@example.com")
    client = login(new_client(), "emp@example.com")
    access = client.cookies.get(ACCESS_COOKIE)
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    assert all("Max-Age=0" in c or "expires=" in c.lower() for c in _set_cookie_headers(response))

    # The (still unexpired) access token no longer works anywhere.
    replay = new_client().get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert replay.status_code == 401
    assert db.scalar("SELECT count(*) FROM audit_logs WHERE action = 'auth.logout'") == 1


def test_login_is_rate_limited(db: Factory, new_client: NewClient) -> None:
    db.user("emp@example.com")
    client = new_client()
    statuses = [
        client.post(
            "/api/v1/auth/login", json={"email": "emp@example.com", "password": "bad"}
        ).status_code
        for _ in range(11)
    ]
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429
    blocked = client.post(
        "/api/v1/auth/login", json={"email": "emp@example.com", "password": TEST_PASSWORD}
    )
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0


def test_change_password_signs_out_other_devices(db: Factory, new_client: NewClient) -> None:
    db.user("emp@example.com")
    laptop = login(new_client(), "emp@example.com")
    phone = login(new_client(), "emp@example.com")

    wrong = laptop.post(
        "/api/v1/auth/change-password",
        json={"current_password": "not-it", "new_password": "Another-Strong-Pass-42"},
    )
    assert wrong.status_code == 401
    weak = laptop.post(
        "/api/v1/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "short"},
    )
    assert weak.status_code == 422

    ok = laptop.post(
        "/api/v1/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "Another-Strong-Pass-42"},
    )
    assert ok.status_code == 200, ok.text
    sync_csrf(laptop)
    assert laptop.get("/api/v1/auth/me").status_code == 200
    assert phone.get("/api/v1/auth/me").status_code == 401
    login(new_client(), "emp@example.com", "Another-Strong-Pass-42")


def test_password_reset_flow(db: Factory, new_client: NewClient, api_app: FastAPI) -> None:
    db.user("emp@example.com")
    session = login(new_client(), "emp@example.com")
    anon = new_client()

    unknown = anon.post("/api/v1/auth/password-reset/request", json={"email": "ghost@example.com"})
    known = anon.post("/api/v1/auth/password-reset/request", json={"email": "emp@example.com"})
    assert unknown.status_code == known.status_code == 202
    assert unknown.json() == known.json()  # no account enumeration
    sent = api_app.state.reset_notifier.sent
    assert len(sent) == 1
    token = parse_qs(urlparse(sent[0]["reset_url"]).query)["token"][0]
    assert (
        db.scalar("SELECT count(*) FROM password_reset_tokens WHERE token_hash = :t", t=token) == 0
    )

    done = anon.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "Brand-New-Secret-77"},
    )
    assert done.status_code == 200, done.text
    assert session.get("/api/v1/auth/me").status_code == 401  # existing sessions revoked
    login(new_client(), "emp@example.com", "Brand-New-Secret-77")

    again = anon.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "Brand-New-Secret-88"},
    )
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "invalid_reset_token"
