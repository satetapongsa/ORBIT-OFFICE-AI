"""Notifications: produced by real account events, visible only to their recipient."""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.security import CSRF_HEADER
from app.services.notifications import _safe_link
from tests.conftest import TEST_PASSWORD, Factory, login, sync_csrf

NewClient = Callable[[], TestClient]
AsUser = Callable[..., TestClient]

BASE = "/api/v1/notifications"


def _add(db: Factory, user_id: uuid.UUID, title: str, *, read: bool = False) -> uuid.UUID:
    with db.engine.begin() as conn:
        return uuid.UUID(
            str(
                conn.scalar(
                    text(
                        "INSERT INTO notifications (user_id, type, title, body, read_at)"
                        " VALUES (:u, 'SYSTEM', :t, '', CASE WHEN :r THEN now() END) RETURNING id"
                    ),
                    {"u": user_id, "t": title, "r": read},
                )
            )
        )


def _me(client: TestClient) -> uuid.UUID:
    return uuid.UUID(client.get("/api/v1/auth/me").json()["user"]["id"])


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", BASE),
        ("GET", f"{BASE}/unread-count"),
        ("POST", f"{BASE}/read-all"),
        ("POST", f"{BASE}/{uuid.uuid4()}/read"),
    ],
)
def test_notifications_require_authentication(
    new_client: NewClient, method: str, path: str
) -> None:
    response = new_client().request(method, path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_list_is_newest_first_with_unread_count_and_filter(db: Factory, as_user: AsUser) -> None:
    client = as_user(["EMPLOYEE"])
    me = _me(client)
    _add(db, me, "old", read=True)
    _add(db, me, "middle")
    _add(db, me, "new")

    body = client.get(BASE).json()
    assert [n["title"] for n in body["items"]] == ["new", "middle", "old"]
    assert body["total"] == 3
    assert body["unread_count"] == 2

    unread = client.get(BASE, params={"unread_only": "true"}).json()
    assert [n["title"] for n in unread["items"]] == ["new", "middle"]

    page2 = client.get(BASE, params={"page": 2, "page_size": 2}).json()
    assert [n["title"] for n in page2["items"]] == ["old"]
    assert client.get(f"{BASE}/unread-count").json() == {"unread_count": 2}


def test_users_never_see_or_change_other_users_notifications(db: Factory, as_user: AsUser) -> None:
    alice = as_user(["EMPLOYEE"])
    bob = as_user(["ADMIN"])  # even an administrator cannot read someone else's inbox
    alice_note = _add(db, _me(alice), "for alice")

    assert bob.get(BASE).json()["items"] == []
    assert bob.post(f"{BASE}/{alice_note}/read").status_code == 404
    bob.post(f"{BASE}/read-all")
    assert db.scalar("SELECT read_at FROM notifications WHERE id = :i", i=alice_note) is None
    assert alice.get(f"{BASE}/unread-count").json() == {"unread_count": 1}


def test_mark_one_and_all_read(db: Factory, as_user: AsUser) -> None:
    client = as_user(["EMPLOYEE"])
    me = _me(client)
    first = _add(db, me, "first")
    _add(db, me, "second")

    marked = client.post(f"{BASE}/{first}/read")
    assert marked.status_code == 200
    assert marked.json()["read_at"] is not None
    again = client.post(f"{BASE}/{first}/read")  # idempotent, keeps the first read time
    assert again.json()["read_at"] == marked.json()["read_at"]
    assert client.get(f"{BASE}/unread-count").json() == {"unread_count": 1}

    result = client.post(f"{BASE}/read-all").json()
    assert result == {"updated": 1, "unread_count": 0}


def test_state_changes_require_csrf(db: Factory, as_user: AsUser) -> None:
    client = as_user(["EMPLOYEE"])
    note = _add(db, _me(client), "x")
    del client.headers[CSRF_HEADER]
    assert client.post(f"{BASE}/read-all").status_code == 403
    assert client.post(f"{BASE}/{note}/read").status_code == 403


def test_password_change_notifies_the_user(db: Factory, new_client: NewClient) -> None:
    db.user("emp@example.com")
    client = login(new_client(), "emp@example.com")
    ok = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": TEST_PASSWORD, "new_password": "Another-Strong-Pass-42"},
    )
    assert ok.status_code == 200
    sync_csrf(client)
    items = client.get(BASE).json()["items"]
    assert [(n["type"], n["title"]) for n in items] == [("SECURITY", "รหัสผ่านของคุณถูกเปลี่ยนแล้ว")]
    assert items[0]["link_url"] == "/account"


def test_admin_changes_notify_the_affected_user_only(db: Factory, as_user: AsUser) -> None:
    admin = as_user(["ADMIN"])
    created = admin.post(
        "/api/v1/users",
        json={
            "employee_code": "E-500",
            "email": "target@example.com",
            "first_name": "เป้า",
            "last_name": "หมาย",
            "password": "Brand-New-Strong-Pass-42",
        },
    )
    assert created.status_code == 201, created.text
    target_id = created.json()["id"]

    assert (
        admin.put(
            f"/api/v1/users/{target_id}/roles", json={"role_codes": ["EMPLOYEE", "MANAGER"]}
        ).status_code
        == 200
    )
    assert (
        admin.patch(f"/api/v1/users/{target_id}", json={"job_title": "หัวหน้าทีม"}).status_code == 200
    )

    with db.engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT type, title, body FROM notifications WHERE user_id = :u ORDER BY created_at"
            ),
            {"u": target_id},
        ).all()
    assert [r[0] for r in rows] == ["ACCOUNT", "ACCOUNT", "ACCOUNT"]
    assert rows[0][1] == "ยินดีต้อนรับสู่ ORBIT OFFICE AI"
    assert "ผู้จัดการ" in rows[1][2]  # role name, not code
    assert "ตำแหน่ง" in rows[2][2]
    assert admin.get(BASE).json()["total"] == 0  # the actor is not notified


def test_database_rejects_external_links(db: Factory) -> None:
    uid = db.user("emp@example.com")
    for bad in ("https://evil.example.com", "//evil.example.com"):
        with pytest.raises(IntegrityError), db.engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO notifications (user_id, type, title, body, link_url)"
                    " VALUES (:u, 'SYSTEM', 't', '', :l)"
                ),
                {"u": uid, "l": bad},
            )


@pytest.mark.parametrize("bad", ["https://evil.example.com", "//evil", "/\\evil", "account"])
def test_service_rejects_non_relative_links(bad: str) -> None:
    with pytest.raises(ValueError, match="relative"):
        _safe_link(bad)


def test_service_accepts_in_app_paths() -> None:
    assert _safe_link("/account") == "/account"
    assert _safe_link(None) is None
