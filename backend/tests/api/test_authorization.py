"""Backend-enforced RBAC: every system role against the protected endpoints."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from tests.conftest import Factory, login

AsUser = Callable[..., TestClient]

# (method, path, body) → expected status per role. 2xx = allowed, 403 = denied by RBAC.
READ_ENDPOINTS = [
    ("GET", "/api/v1/users"),
    ("GET", "/api/v1/departments"),
    ("GET", "/api/v1/roles"),
    ("GET", "/api/v1/permissions"),
    ("GET", "/api/v1/audit-logs"),
]

EXPECTED_READ = {
    #               users dept  roles perms audit
    "EMPLOYEE": (403, 200, 403, 403, 403),
    "MANAGER": (200, 200, 403, 403, 403),
    "HR": (200, 200, 403, 403, 403),
    "IT_SUPPORT": (200, 200, 403, 403, 403),
    "ADMIN": (200, 200, 200, 200, 200),
}


@pytest.mark.parametrize("role", sorted(EXPECTED_READ))
def test_read_access_matrix(as_user: AsUser, role: str) -> None:
    client = as_user([role])
    actual = tuple(client.request(m, p).status_code for m, p in READ_ENDPOINTS)
    assert actual == EXPECTED_READ[role]


@pytest.mark.parametrize(
    ("role", "expected"),
    [("EMPLOYEE", 403), ("MANAGER", 403), ("IT_SUPPORT", 403), ("HR", 201), ("ADMIN", 201)],
)
def test_only_department_managers_can_create_departments(
    as_user: AsUser, role: str, expected: int
) -> None:
    response = as_user([role]).post(
        "/api/v1/departments", json={"code": f"D{role[:3]}", "name": "x"}
    )
    assert response.status_code == expected, response.text


def test_permission_denied_uses_error_envelope(as_user: AsUser) -> None:
    response = as_user(["EMPLOYEE"]).get("/api/v1/users")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


def test_hr_can_create_employees_but_not_assign_privileged_roles(as_user: AsUser) -> None:
    hr = as_user(["HR"])
    created = hr.post(
        "/api/v1/users",
        json={
            "employee_code": "E-100",
            "email": "new@example.com",
            "first_name": "ใหม่",
            "last_name": "พนักงาน",
        },
    )
    assert created.status_code == 201, created.text
    assert [r["code"] for r in created.json()["roles"]] == ["EMPLOYEE"]

    escalate = hr.post(
        "/api/v1/users",
        json={
            "employee_code": "E-101",
            "email": "boss@example.com",
            "first_name": "a",
            "last_name": "b",
            "role_codes": ["ADMIN"],
        },
    )
    assert escalate.status_code == 403
    user_id = created.json()["id"]
    assert (
        hr.put(f"/api/v1/users/{user_id}/roles", json={"role_codes": ["ADMIN"]}).status_code == 403
    )


def test_cannot_grant_permissions_you_do_not_hold(db: Factory, as_user: AsUser) -> None:
    admin = as_user(["ADMIN"])
    role = admin.post(
        "/api/v1/roles",
        json={
            "code": "ROLE_ASSIGNER",
            "name": "ผู้กำหนดบทบาท",
            "permissions": ["roles:assign", "roles:read", "users:read"],
        },
    )
    assert role.status_code == 201, role.text

    assigner = as_user(["ROLE_ASSIGNER"])
    me = assigner.get("/api/v1/auth/me").json()["user"]
    to_admin = assigner.put(f"/api/v1/users/{me['id']}/roles", json={"role_codes": ["ADMIN"]})
    assert to_admin.status_code == 403
    assert to_admin.json()["error"]["details"]  # lists the permissions the actor lacks

    # Role managers also cannot add permissions they do not hold to a role.
    admin.post(
        "/api/v1/roles",
        json={"code": "ROLE_EDITOR", "name": "x", "permissions": ["roles:manage", "roles:read"]},
    )
    editor = as_user(["ROLE_EDITOR"])
    target = admin.post(
        "/api/v1/roles", json={"code": "TEAM_LEAD", "name": "x", "permissions": []}
    ).json()
    sneaky = editor.put(
        f"/api/v1/roles/{target['id']}/permissions", json={"permissions": ["audit:read"]}
    )
    assert sneaky.status_code == 403


def test_admin_role_permissions_are_locked_and_system_roles_cannot_be_deleted(
    db: Factory, as_user: AsUser
) -> None:
    admin = as_user(["ADMIN"])
    admin_role = db.role_id("ADMIN")
    employee_role = db.role_id("EMPLOYEE")
    assert (
        admin.put(f"/api/v1/roles/{admin_role}/permissions", json={"permissions": []}).status_code
        == 403
    )
    assert admin.delete(f"/api/v1/roles/{employee_role}").status_code == 409


def test_last_admin_is_protected(db: Factory, as_user: AsUser) -> None:
    admin = as_user(["ADMIN", "EMPLOYEE"])
    me = admin.get("/api/v1/auth/me").json()["user"]
    demote = admin.put(f"/api/v1/users/{me['id']}/roles", json={"role_codes": ["EMPLOYEE"]})
    assert demote.status_code == 409
    assert admin.post(f"/api/v1/users/{me['id']}/deactivate").status_code == 409


def test_revoked_role_takes_effect_on_the_next_request(db: Factory, as_user: AsUser) -> None:
    admin = as_user(["ADMIN"])
    hr = as_user(["HR"], email="hr-revoke@example.com")
    assert hr.get("/api/v1/users").status_code == 200

    hr_id = hr.get("/api/v1/auth/me").json()["user"]["id"]
    assert (
        admin.put(f"/api/v1/users/{hr_id}/roles", json={"role_codes": ["EMPLOYEE"]}).status_code
        == 200
    )
    assert hr.get("/api/v1/users").status_code == 403  # same access token, permissions re-read


def test_deactivated_user_is_signed_out_immediately(db: Factory, as_user: AsUser) -> None:
    admin = as_user(["ADMIN"])
    emp = as_user(["EMPLOYEE"], email="leaver@example.com")
    emp_id = emp.get("/api/v1/auth/me").json()["user"]["id"]
    response = admin.post(f"/api/v1/users/{emp_id}/deactivate")
    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert emp.get("/api/v1/auth/me").status_code == 401
    assert emp.post("/api/v1/auth/refresh").status_code == 401


def test_custom_role_grants_exactly_its_permissions(
    db: Factory, as_user: AsUser, new_client: Callable[[], TestClient]
) -> None:
    admin = as_user(["ADMIN"])
    created = admin.post(
        "/api/v1/roles", json={"code": "AUDITOR", "name": "ผู้ตรวจสอบ", "permissions": ["audit:read"]}
    )
    assert created.status_code == 201
    db.user("auditor@example.com", ["AUDITOR"])
    auditor = login(new_client(), "auditor@example.com")
    assert auditor.get("/api/v1/audit-logs").status_code == 200
    assert auditor.get("/api/v1/users").status_code == 403
    assert auditor.get("/api/v1/auth/me").json()["permissions"] == ["audit:read"]


def test_user_management_actions_are_audited(db: Factory, as_user: AsUser) -> None:
    admin = as_user(["ADMIN"])
    dept = admin.post("/api/v1/departments", json={"code": "FIN", "name": "การเงิน"}).json()
    user = admin.post(
        "/api/v1/users",
        json={
            "employee_code": "E-200",
            "email": "fin@example.com",
            "first_name": "a",
            "last_name": "b",
            "department_id": dept["id"],
            "password": "Initial-Strong-Pass-1",
        },
    ).json()
    admin.patch(f"/api/v1/users/{user['id']}", json={"job_title": "นักบัญชี"})
    admin.put(f"/api/v1/users/{user['id']}/roles", json={"role_codes": ["EMPLOYEE", "MANAGER"]})
    admin.post(f"/api/v1/users/{user['id']}/deactivate")

    logs = admin.get("/api/v1/audit-logs", params={"entity_id": user["id"]}).json()
    actions = [item["action"] for item in logs["items"]]
    assert actions == ["user.deactivated", "user.roles_changed", "user.updated", "user.created"]
    roles_change = next(i for i in logs["items"] if i["action"] == "user.roles_changed")
    assert roles_change["details"] == {"added": ["MANAGER"], "removed": []}
    assert "password" not in str(logs).lower().replace("password_", "")


def test_audit_log_is_append_only_in_the_database(db: Factory, as_user: AsUser) -> None:
    as_user(["EMPLOYEE"])  # produces an auth.login entry
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError, match="append-only"), db.engine.begin() as conn:
        conn.execute(text("UPDATE audit_logs SET action = 'tampered'"))
    with pytest.raises(DBAPIError, match="append-only"), db.engine.begin() as conn:
        conn.execute(text("DELETE FROM audit_logs"))


def test_duplicate_email_is_a_conflict(as_user: AsUser) -> None:
    admin = as_user(["ADMIN"], email="dupe-admin@example.com")
    body = {
        "employee_code": "E-300",
        "email": "Dupe-Admin@Example.com",
        "first_name": "a",
        "last_name": "b",
    }
    response = admin.post("/api/v1/users", json=body)
    assert response.status_code == 409


def test_list_users_supports_search_and_pagination(db: Factory, as_user: AsUser) -> None:
    admin = as_user(["ADMIN"])
    for i in range(3):
        db.user(f"sales{i}@example.com")
    page = admin.get("/api/v1/users", params={"q": "sales", "page_size": 2}).json()
    assert page["total"] == 3
    assert len(page["items"]) == 2
    assert page["page_size"] == 2
