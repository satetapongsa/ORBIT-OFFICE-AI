"""Employee Center: directory, profiles, account fields and the protected HR record."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.conftest import Factory

AsUser = Callable[..., TestClient]
BASE = "/api/v1/employees"

HR_RECORD: dict[str, Any] = {
    "date_of_birth": "1990-04-13",
    "national_id_last4": "1234",
    "personal_phone": "081-234-5678",
    "personal_email": "somchai.personal@example.com",
    "address": "99 ถนนสุขุมวิท กรุงเทพฯ",
    "hire_date": "2020-06-01",
    "employment_type": "FULL_TIME",
    "emergency_contact": {"name": "สมหญิง ใจดี", "relationship": "ภรรยา", "phone": "089-999-0000"},
}
HR_KEYS = set(HR_RECORD)


def uid(client: TestClient) -> str:
    return str(client.get("/api/v1/auth/me").json()["user"]["id"])


def test_directory_requires_permission(
    as_user: AsUser, new_client: Callable[[], TestClient]
) -> None:
    assert new_client().get(BASE).status_code == 401
    assert as_user([]).get(BASE).status_code == 403
    assert as_user(["EMPLOYEE"]).get(BASE).status_code == 200


def test_directory_lists_active_people_with_work_details_only(db: Factory, as_user: AsUser) -> None:
    sales = db.department("SALES", "ฝ่ายขาย")
    it = db.department("IT", "ฝ่ายไอที")
    db.user("somchai@example.com", department_id=sales)
    db.user("wichai@example.com", department_id=it)
    db.user("gone@example.com", department_id=sales, active=False)
    viewer = as_user(["EMPLOYEE"], email="viewer@example.com", department_id=sales)

    page = viewer.get(BASE).json()
    emails = {e["email"] for e in page["items"]}
    assert emails == {"somchai@example.com", "wichai@example.com", "viewer@example.com"}
    item = page["items"][0]
    assert set(item) == {
        "id",
        "employee_code",
        "display_name",
        "first_name",
        "last_name",
        "job_title",
        "department",
        "email",
        "phone_work",
        "is_active",
    }
    assert not HR_KEYS & set(item)

    by_dept = viewer.get(BASE, params={"department_id": str(it)}).json()["items"]
    assert [e["email"] for e in by_dept] == ["wichai@example.com"]
    found = viewer.get(BASE, params={"q": "somch"}).json()["items"]
    assert [e["email"] for e in found] == ["somchai@example.com"]
    assert viewer.get(BASE, params={"q": "%"}).json()["total"] == 0  # literal %

    # Inactive accounts need users:read.
    assert viewer.get(BASE, params={"include_inactive": True}).status_code == 403
    hr = as_user(["HR"])
    all_emails = {
        e["email"] for e in hr.get(BASE, params={"include_inactive": True}).json()["items"]
    }
    assert "gone@example.com" in all_emails


def test_profile_sections_follow_permissions(db: Factory, as_user: AsUser) -> None:
    sales = db.department("SALES", "ฝ่ายขาย")
    boss = db.user("boss@example.com", ["MANAGER"], department_id=sales)
    with db.engine.begin() as conn:
        conn.execute(
            text("UPDATE departments SET manager_id = :m WHERE id = :d"), {"m": boss, "d": sales}
        )
    target = db.user("somchai@example.com", department_id=sales)

    employee = as_user(["EMPLOYEE"]).get(f"{BASE}/{target}").json()
    assert employee["department_manager"]["display_name"] == "boss@example.com"
    assert employee["account"] is None
    assert employee["capabilities"] == {
        "can_edit_account": False,
        "can_manage_roles": False,
        "can_change_active": False,
        "can_view_hr": False,
        "can_edit_hr": False,
    }
    assert not HR_KEYS & set(employee)

    hr = as_user(["HR"]).get(f"{BASE}/{target}").json()
    assert hr["account"]["roles"][0]["code"] == "EMPLOYEE"
    assert hr["capabilities"]["can_view_hr"] and hr["capabilities"]["can_edit_hr"]
    assert hr["capabilities"]["can_edit_account"] is True
    assert hr["capabilities"]["can_manage_roles"] is False  # HR holds no roles:assign

    admin = as_user(["ADMIN"]).get(f"{BASE}/{target}").json()["capabilities"]
    assert all(admin.values())

    manager = as_user(["MANAGER"]).get(f"{BASE}/{target}").json()
    assert manager["account"] is not None  # users:read
    assert manager["capabilities"]["can_view_hr"] is False


def test_inactive_profile_hidden_without_users_read(db: Factory, as_user: AsUser) -> None:
    gone = db.user("gone@example.com", active=False)
    assert as_user(["EMPLOYEE"]).get(f"{BASE}/{gone}").status_code == 404
    assert as_user(["HR"]).get(f"{BASE}/{gone}").status_code == 200
    assert as_user(["EMPLOYEE"]).get(f"{BASE}/{uuid.uuid4()}").status_code == 404


def test_hr_record_is_protected_and_audited(db: Factory, as_user: AsUser) -> None:
    somchai = as_user(["EMPLOYEE"], email="somchai@example.com")
    somchai_id = uid(somchai)
    url = f"{BASE}/{somchai_id}/hr"

    # Nobody without employees:read_sensitive can read someone else's record.
    for role in ("EMPLOYEE", "MANAGER", "IT_SUPPORT"):
        assert as_user([role]).get(url).status_code == 403
    # Only HR-type roles may write it — not even the employee themself.
    assert somchai.put(url, json=HR_RECORD).status_code == 403
    assert as_user(["MANAGER"]).put(url, json=HR_RECORD).status_code == 403

    empty = somchai.get(url).json()
    assert empty["exists"] is False

    hr = as_user(["HR"], email="hr@example.com")
    saved = hr.put(url, json=HR_RECORD)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["exists"] is True
    assert body["national_id_last4"] == "1234"
    assert body["emergency_contact"]["relationship"] == "ภรรยา"
    assert body["updated_by"]["display_name"] == "hr@example.com"

    # The employee sees their own record (not audited); HR reads are audited.
    assert somchai.get(url).json()["personal_phone"] == "081-234-5678"
    assert hr.get(url).status_code == 200
    viewed = db.scalar(
        "SELECT count(*) FROM audit_logs WHERE action = 'employee.hr_profile_viewed'"
        " AND entity_id = :i",
        i=somchai_id,
    )
    assert viewed == 1

    # The audit log keeps field names only, never the values.
    details = db.scalar(
        "SELECT metadata::text FROM audit_logs WHERE action = 'employee.hr_profile_updated'"
    )
    assert "national_id_last4" in details
    assert "1234" not in details and "081-234-5678" not in details

    # Replacing the record clears omitted fields.
    cleared = hr.put(url, json={"hire_date": "2020-06-01"}).json()
    assert cleared["national_id_last4"] is None
    assert cleared["emergency_contact"] is None


def test_hr_record_validation(as_user: AsUser) -> None:
    target = uid(as_user(["EMPLOYEE"]))
    hr = as_user(["HR"])
    url = f"{BASE}/{target}/hr"
    for bad in (
        {"national_id_last4": "1234567890123"},  # never the full national ID
        {"national_id_last4": "12a4"},
        {"personal_email": "not-an-email"},
        {"employment_type": "SLAVE"},
        {"emergency_contact": {"name": "", "relationship": "x", "phone": "1"}},
    ):
        assert hr.put(url, json=bad).status_code == 422, bad
    assert hr.put(f"{BASE}/{uuid.uuid4()}/hr", json={}).status_code == 404
