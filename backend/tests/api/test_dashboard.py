"""Dashboard summary: real data, sections scoped to the caller's permissions."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.services.dashboard import PERIOD_DAYS, _period
from tests.conftest import Factory, login

NewClient = Callable[[], TestClient]
AsUser = Callable[..., TestClient]

URL = "/api/v1/dashboard/summary"
BANGKOK = ZoneInfo("Asia/Bangkok")


def _summary(client: TestClient) -> dict:  # type: ignore[type-arg]
    response = client.get(URL)
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def _doc(db: Factory, owner: uuid.UUID, dept: uuid.UUID | None, visibility: str) -> None:
    with db.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO documents (title, owner_id, department_id, visibility, status)"
                " VALUES ('d', :o, :d, :v, 'ACTIVE')"
            ),
            {"o": owner, "d": dept, "v": visibility},
        )


def test_dashboard_requires_authentication(new_client: NewClient) -> None:
    assert new_client().get(URL).status_code == 401


# documents / organization / security present?
EXPECTED_SECTIONS = {
    "EMPLOYEE": (True, False, False),
    "MANAGER": (True, True, False),
    "HR": (True, True, False),
    "IT_SUPPORT": (True, True, False),
    "ADMIN": (True, True, True),
}


@pytest.mark.parametrize("role", sorted(EXPECTED_SECTIONS))
def test_sections_follow_permissions(as_user: AsUser, role: str) -> None:
    body = _summary(as_user([role]))
    present = tuple(body[k] is not None for k in ("documents", "organization", "security"))
    assert present == EXPECTED_SECTIONS[role]
    # Personal sections are always present.
    assert body["account"]["roles"][0]["code"] == role
    assert len(body["my_activity"]["daily_sign_ins"]) == PERIOD_DAYS


def test_user_without_permissions_sees_only_personal_sections(as_user: AsUser) -> None:
    body = _summary(as_user([]))
    assert body["documents"] is None
    assert body["organization"] is None
    assert body["security"] is None
    assert body["account"]["roles"] == []


def test_account_sessions_and_previous_login(db: Factory, new_client: NewClient) -> None:
    dept = db.department("SALES", "ฝ่ายขาย")
    db.user("emp@example.com", department_id=dept)
    laptop = login(new_client(), "emp@example.com")
    first = _summary(laptop)["account"]
    assert first["active_sessions"] == 1
    assert first["previous_login_at"] is None
    assert first["department"]["code"] == "SALES"

    phone = login(new_client(), "emp@example.com")
    account = _summary(phone)["account"]
    assert account["active_sessions"] == 2
    assert account["previous_login_at"] is not None

    phone.post("/api/v1/auth/logout")
    assert _summary(laptop)["account"]["active_sessions"] == 1


def test_my_activity_contains_only_my_events(db: Factory, as_user: AsUser) -> None:
    me = as_user(["EMPLOYEE"], email="me@example.com")
    as_user(["EMPLOYEE"], email="other@example.com")  # another user's login
    body = _summary(me)

    today = datetime.now(BANGKOK).date().isoformat()
    sign_ins = body["my_activity"]["daily_sign_ins"]
    assert sign_ins[-1] == {"date": today, "count": 1}
    assert sum(d["count"] for d in sign_ins) == 1

    recent = body["my_activity"]["recent"]
    assert [item["action"] for item in recent] == ["auth.login"]
    assert recent[0]["actor"]["display_name"] == "me@example.com"
    # Reduced shape: no IP address, user agent or metadata.
    assert set(recent[0]) == {"id", "action", "occurred_at", "actor", "entity_type"}


def test_my_activity_includes_changes_made_to_my_account(db: Factory, as_user: AsUser) -> None:
    admin = as_user(["ADMIN"], email="admin@example.com")
    me = as_user(["EMPLOYEE"], email="me@example.com")
    my_id = me.get("/api/v1/auth/me").json()["user"]["id"]
    assert admin.patch(f"/api/v1/users/{my_id}", json={"job_title": "x"}).status_code == 200

    recent = _summary(me)["my_activity"]["recent"]
    assert recent[0]["action"] == "user.updated"
    assert recent[0]["actor"]["display_name"] == "admin@example.com"


def test_document_count_uses_the_access_predicate(db: Factory, as_user: AsUser) -> None:
    sales = db.department("SALES")
    hr = db.department("HR")
    owner = db.user("owner@example.com", department_id=hr)
    _doc(db, owner, hr, "COMPANY")  # everyone
    _doc(db, owner, hr, "DEPARTMENT")  # HR only
    _doc(db, owner, hr, "PRIVATE")  # owner only

    employee = as_user(["EMPLOYEE"], department_id=sales)
    assert _summary(employee)["documents"] == {"accessible_count": 1}
    colleague = as_user(["EMPLOYEE"], department_id=hr)
    assert _summary(colleague)["documents"] == {"accessible_count": 2}
    admin = as_user(["ADMIN"])  # documents:manage override
    assert _summary(admin)["documents"] == {"accessible_count": 3}


def test_organization_counts(db: Factory, as_user: AsUser) -> None:
    sales = db.department("SALES", "ฝ่ายขาย")
    closed = db.department("OLD", "แผนกที่ปิดแล้ว")
    db.user("a@example.com", department_id=sales)
    db.user("b@example.com", department_id=sales)
    db.user("c@example.com", department_id=closed)
    db.user("gone@example.com", department_id=sales, active=False)
    with db.engine.begin() as conn:
        conn.execute(text("UPDATE departments SET deleted_at = now() WHERE id = :i"), {"i": closed})

    org = _summary(as_user(["HR"]))["organization"]  # the HR user has no department
    assert org["active_users"] == 4
    assert org["inactive_users"] == 1
    assert org["departments"] == 1
    by_dept = [
        ((d["department"] or {}).get("code"), d["count"]) for d in org["users_by_department"]
    ]
    # Users of the deleted department and the HR user count as "no department".
    assert by_dept == [("SALES", 2), (None, 2)]


def test_security_section_counts_sign_ins_and_failures(db: Factory, new_client: NewClient) -> None:
    db.user("admin@example.com", ["ADMIN"])
    db.user("emp@example.com")
    bad = new_client().post(
        "/api/v1/auth/login", json={"email": "emp@example.com", "password": "wrong-password"}
    )
    assert bad.status_code == 401
    login(new_client(), "emp@example.com")
    admin = login(new_client(), "admin@example.com")

    security = _summary(admin)["security"]
    assert security["sign_ins"] == 2
    assert security["failed_sign_ins"] == 1
    assert security["daily"][-1]["sign_ins"] == 2
    assert security["daily"][-1]["failed_sign_ins"] == 1
    assert len(security["daily"]) == PERIOD_DAYS
    assert security["recent"][0]["action"] == "auth.login"
    assert set(security["recent"][0]) == {"id", "action", "occurred_at", "actor", "entity_type"}


def test_days_are_grouped_in_the_business_time_zone(db: Factory, as_user: AsUser) -> None:
    client = as_user(["EMPLOYEE"], email="me@example.com")
    me = client.get("/api/v1/auth/me").json()["user"]["id"]
    # 00:30 Bangkok time today is still "yesterday" in UTC.
    today = datetime.now(BANGKOK).date()
    early = datetime.combine(today, time(0, 30), tzinfo=BANGKOK)
    with db.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO audit_logs (occurred_at, actor_id, action, metadata)"
                " VALUES (:t, :a, 'auth.login', '{}')"
            ),
            {"t": early.astimezone(UTC), "a": me},
        )
    sign_ins = _summary(client)["my_activity"]["daily_sign_ins"]
    assert sign_ins[-1] == {"date": today.isoformat(), "count": 2}


def test_period_boundaries() -> None:
    now = datetime(2026, 11, 10, 18, 30, tzinfo=UTC)  # 01:30 on 11 Nov in Bangkok
    days, start = _period(now, "Asia/Bangkok")
    assert days[-1] == date(2026, 11, 11)
    assert days[0] == date(2026, 11, 11) - timedelta(days=PERIOD_DAYS - 1)
    assert start == datetime(2026, 10, 28, 17, 0, tzinfo=UTC)
    assert len(days) == PERIOD_DAYS
