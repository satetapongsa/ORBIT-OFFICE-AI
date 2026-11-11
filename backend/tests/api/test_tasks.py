"""Task management: visibility, capabilities, assignment scope, comments, attachments, history."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import Factory
from tests.document_support import THAI_TEXT, MemoryStorage

AsUser = Callable[..., TestClient]
BASE = "/api/v1/tasks"


@dataclass
class Team:
    """Two departments with a manager and employees, plus an administrator."""

    db: Factory
    storage: MemoryStorage
    sales: uuid.UUID
    it: uuid.UUID
    manager: TestClient  # MANAGER in SALES
    alice: TestClient  # EMPLOYEE in SALES
    bob: TestClient  # EMPLOYEE in SALES
    it_manager: TestClient  # MANAGER in IT
    carol: TestClient  # EMPLOYEE in IT
    admin: TestClient  # ADMIN, no department


@pytest.fixture
def team(api_app: FastAPI, db: Factory, as_user: AsUser) -> Team:
    storage = MemoryStorage()
    api_app.state.document_storage = storage
    sales = db.department("SALES", "ฝ่ายขาย")
    it = db.department("IT", "ฝ่ายไอที")
    return Team(
        db=db,
        storage=storage,
        sales=sales,
        it=it,
        manager=as_user(["MANAGER"], email="manager@example.com", department_id=sales),
        alice=as_user(["EMPLOYEE"], email="alice@example.com", department_id=sales),
        bob=as_user(["EMPLOYEE"], email="bob@example.com", department_id=sales),
        it_manager=as_user(["MANAGER"], email="itm@example.com", department_id=it),
        carol=as_user(["EMPLOYEE"], email="carol@example.com", department_id=it),
        admin=as_user(["ADMIN"], email="admin@example.com"),
    )


def uid(client: TestClient) -> str:
    return str(client.get("/api/v1/auth/me").json()["user"]["id"])


def create(client: TestClient, title: str = "เตรียมรายงานยอดขาย", **fields: Any) -> dict[str, Any]:
    response = client.post(BASE, json={"title": title, **fields})
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def titles(client: TestClient, **params: Any) -> set[str]:
    response = client.get(BASE, params=params)
    assert response.status_code == 200, response.text
    return {t["title"] for t in response.json()["items"]}


def notifications_for(db: Factory, email: str) -> list[str]:
    with db.engine.connect() as conn:
        from sqlalchemy import text

        rows = conn.execute(
            text(
                "SELECT n.title FROM notifications n JOIN users u ON u.id = n.user_id"
                " WHERE u.email = :e AND n.type = 'TASK' ORDER BY n.created_at"
            ),
            {"e": email},
        )
        return [r[0] for r in rows]


# --- Authentication and route guards ------------------------------------------------------


def test_tasks_require_authentication(new_client: Callable[[], TestClient]) -> None:
    client = new_client()
    assert client.get(BASE).status_code == 401
    assert client.post(BASE, json={"title": "x"}).status_code == 401


def test_user_without_task_permissions_is_denied(team: Team, as_user: AsUser) -> None:
    nobody = as_user([])
    assert nobody.get(BASE).status_code == 403
    assert nobody.post(BASE, json={"title": "x"}).status_code == 403
    assert nobody.get(f"{BASE}/assignable-users").status_code == 403


# --- Creation and assignment --------------------------------------------------------------


def test_employee_creates_personal_task(team: Team) -> None:
    due = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    body = create(team.alice, priority="HIGH", due_at=due, description="ใช้ข้อมูลไตรมาส 3")

    assert body["status"] == "TODO"
    assert body["priority"] == "HIGH"
    assert body["department"]["code"] == "SALES"  # the creator's department
    assert [a["id"] for a in body["assignees"]] == [uid(team.alice)]  # assigned to self
    assert body["is_overdue"] is False
    caps = body["capabilities"]
    assert caps["can_edit"] and caps["can_delete"] and caps["can_cancel"]
    assert caps["can_assign"] is False  # employees hold no tasks:assign

    events = team.alice.get(f"{BASE}/{body['id']}/history").json()
    assert {e["event_type"] for e in events} == {"CREATED", "ASSIGNED"}
    assert team.db.scalar(
        "SELECT count(*) FROM audit_logs WHERE action = 'task.created' AND entity_id = :i",
        i=body["id"],
    )
    assert notifications_for(team.db, "alice@example.com") == []  # no self-notification


def test_employee_cannot_assign_someone_else(team: Team) -> None:
    response = team.alice.post(BASE, json={"title": "งาน", "assignee_ids": [uid(team.bob)]})
    assert response.status_code == 403


def test_employee_cannot_create_in_another_department(team: Team) -> None:
    response = team.alice.post(BASE, json={"title": "งาน", "department_id": str(team.it)})
    assert response.status_code == 403
    # An administrator may.
    body = create(team.admin, department_id=str(team.it), assignee_ids=[uid(team.carol)])
    assert body["department"]["code"] == "IT"


def test_manager_assigns_within_own_department_only(team: Team) -> None:
    body = create(team.manager, assignee_ids=[uid(team.alice), uid(team.bob)])
    assert {a["display_name"] for a in body["assignees"]} == {
        "alice@example.com",
        "bob@example.com",
    }
    assert notifications_for(team.db, "alice@example.com") == [
        "คุณได้รับมอบหมายงาน: เตรียมรายงานยอดขาย"
    ]

    cross = team.manager.post(BASE, json={"title": "ข้ามแผนก", "assignee_ids": [uid(team.carol)]})
    assert cross.status_code == 422
    assert cross.json()["error"]["details"][0]["field"] == "assignees.0"

    unknown = team.manager.post(BASE, json={"title": "x", "assignee_ids": [str(uuid.uuid4())]})
    assert unknown.status_code == 422


def test_inactive_user_cannot_be_assigned(team: Team) -> None:
    ghost = team.db.user("ghost@example.com", department_id=team.sales, active=False)
    response = team.manager.post(BASE, json={"title": "x", "assignee_ids": [str(ghost)]})
    assert response.status_code == 422


def test_replace_assignees(team: Team) -> None:
    task = create(team.manager, assignee_ids=[uid(team.alice)])
    response = team.manager.put(
        f"{BASE}/{task['id']}/assignees", json={"user_ids": [uid(team.bob)]}
    )
    assert response.status_code == 200, response.text
    assert [a["display_name"] for a in response.json()["assignees"]] == ["bob@example.com"]

    events = [e["event_type"] for e in team.manager.get(f"{BASE}/{task['id']}/history").json()]
    assert events.count("UNASSIGNED") == 1
    # Alice lost access; Bob was notified.
    assert team.alice.get(f"{BASE}/{task['id']}").status_code == 404
    assert notifications_for(team.db, "bob@example.com") == ["คุณได้รับมอบหมายงาน: เตรียมรายงานยอดขาย"]
    # Assignees cannot reassign.
    denied = team.bob.put(f"{BASE}/{task['id']}/assignees", json={"user_ids": [uid(team.bob)]})
    assert denied.status_code == 403


# --- Visibility ---------------------------------------------------------------------------


def test_visibility_follows_ownership_assignment_and_department(
    team: Team, as_user: AsUser
) -> None:
    create(team.alice, "งานของอลิซ")
    create(team.manager, "งานที่มอบให้บ็อบ", assignee_ids=[uid(team.bob)])
    create(team.it_manager, "งานไอที", assignee_ids=[uid(team.carol)])

    assert titles(team.alice) == {"งานของอลิซ"}
    assert titles(team.bob) == {"งานที่มอบให้บ็อบ"}
    assert titles(team.carol) == {"งานไอที"}
    assert titles(team.manager) == {"งานของอลิซ", "งานที่มอบให้บ็อบ"}  # whole SALES department
    assert titles(team.it_manager) == {"งานไอที"}
    assert titles(team.admin) == {"งานของอลิซ", "งานที่มอบให้บ็อบ", "งานไอที"}


def test_invisible_tasks_answer_404_everywhere(team: Team) -> None:
    task = create(team.alice, "ส่วนตัว")
    path = f"{BASE}/{task['id']}"
    for client in (team.bob, team.carol, team.it_manager):
        assert client.get(path).status_code == 404
        assert client.patch(path, json={"title": "x"}).status_code == 404
        assert client.post(f"{path}/status", json={"status": "COMPLETED"}).status_code == 404
        assert client.get(f"{path}/comments").status_code == 404
        assert client.post(f"{path}/comments", json={"body": "hi"}).status_code == 404
        assert client.get(f"{path}/attachments").status_code == 404
        assert client.get(f"{path}/history").status_code == 404
        assert client.delete(path).status_code == 404
    assert team.alice.get(f"{BASE}/{uuid.uuid4()}").status_code == 404


def test_department_scope_requires_department_permission(team: Team) -> None:
    assert team.alice.get(BASE, params={"scope": "department"}).status_code == 403
    assert team.manager.get(BASE, params={"scope": "department"}).status_code == 200


# --- Capabilities -------------------------------------------------------------------------


def test_assignee_can_progress_but_not_edit_cancel_or_delete(team: Team) -> None:
    task = create(team.manager, assignee_ids=[uid(team.bob)])
    path = f"{BASE}/{task['id']}"
    caps = team.bob.get(path).json()["capabilities"]
    assert caps == {
        "can_edit": False,
        "can_change_status": True,
        "can_cancel": False,
        "can_assign": False,
        "can_delete": False,
        "can_comment": True,
        "can_attach": True,
    }

    done = team.bob.post(f"{path}/status", json={"status": "COMPLETED"})
    assert done.status_code == 200
    assert done.json()["completed_at"] is not None
    assert notifications_for(team.db, "manager@example.com") == ["งานเสร็จสิ้น: เตรียมรายงานยอดขาย"]
    reopened = team.bob.post(f"{path}/status", json={"status": "IN_PROGRESS"}).json()
    assert reopened["completed_at"] is None

    assert team.bob.patch(path, json={"title": "แก้ชื่อ"}).status_code == 403
    assert team.bob.post(f"{path}/status", json={"status": "CANCELLED"}).status_code == 403
    assert team.bob.delete(path).status_code == 403


def test_manager_edits_and_deletes_department_task(team: Team) -> None:
    task = create(team.alice, "งานของอลิซ")
    path = f"{BASE}/{task['id']}"
    updated = team.manager.patch(path, json={"title": "ชื่อใหม่", "priority": "URGENT"})
    assert updated.status_code == 200
    assert updated.json()["title"] == "ชื่อใหม่"
    assert updated.json()["priority"] == "URGENT"
    # Moving to another department needs tasks:manage_all.
    assert team.manager.patch(path, json={"department_id": str(team.it)}).status_code == 403
    moved = team.admin.patch(path, json={"department_id": str(team.it)})
    assert moved.status_code == 200
    assert team.manager.get(path).status_code == 404  # no longer in SALES
    assert team.it_manager.get(path).status_code == 200

    assert team.it_manager.delete(path).status_code == 204
    assert team.alice.get(path).status_code == 404
    assert titles(team.admin) == set()
    assert team.db.scalar("SELECT deleted_at IS NOT NULL FROM tasks WHERE id = :i", i=task["id"])


def test_clearing_fields_and_noop_update(team: Team) -> None:
    due = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    task = create(team.alice, due_at=due, description="รายละเอียด")
    path = f"{BASE}/{task['id']}"
    cleared = team.alice.patch(path, json={"due_at": None, "description": None}).json()
    assert cleared["due_at"] is None
    assert cleared["description"] is None
    before = len(team.alice.get(f"{path}/history").json())
    assert team.alice.patch(path, json={"title": task["title"]}).status_code == 200
    assert len(team.alice.get(f"{path}/history").json()) == before  # nothing recorded


def test_due_dates_must_have_a_time_zone(team: Team) -> None:
    response = team.alice.post(BASE, json={"title": "x", "due_at": "2026-12-01T10:00:00"})
    assert response.status_code == 422


# --- Lists ----------------------------------------------------------------------------------


def test_scopes_filters_search_and_sort(team: Team) -> None:
    now = datetime.now(UTC)
    late = create(team.manager, "ส่งใบเสนอราคา", assignee_ids=[uid(team.alice)])
    team.manager.patch(
        f"{BASE}/{late['id']}", json={"due_at": (now - timedelta(days=1)).isoformat()}
    )
    create(team.manager, "ประชุม 100% ทีม", assignee_ids=[uid(team.bob)], priority="URGENT")
    create(
        team.alice,
        "สรุปยอด",
        priority="LOW",
        due_at=(now + timedelta(days=5)).isoformat(),
    )

    assert titles(team.alice, scope="assigned") == {"ส่งใบเสนอราคา", "สรุปยอด"}
    assert titles(team.alice, scope="created") == {"สรุปยอด"}
    assert titles(team.manager, scope="department") == {
        "ส่งใบเสนอราคา",
        "ประชุม 100% ทีม",
        "สรุปยอด",
    }
    assert titles(team.manager, overdue=True) == {"ส่งใบเสนอราคา"}
    assert titles(team.manager, priority="URGENT") == {"ประชุม 100% ทีม"}
    assert titles(team.manager, q="100%") == {"ประชุม 100% ทีม"}  # % is literal
    assert titles(team.manager, q="%") == {"ประชุม 100% ทีม"}
    assert titles(team.manager, assignee_id=uid(team.bob)) == {"ประชุม 100% ทีม"}

    items = team.manager.get(BASE, params={"sort": "due"}).json()["items"]
    assert [t["title"] for t in items] == ["ส่งใบเสนอราคา", "สรุปยอด", "ประชุม 100% ทีม"]
    assert items[0]["is_overdue"] is True
    items = team.manager.get(BASE, params={"sort": "priority"}).json()["items"]
    assert items[0]["title"] == "ประชุม 100% ทีม"

    team.alice.post(f"{BASE}/{late['id']}/status", json={"status": "COMPLETED"})
    assert titles(team.manager, overdue=True) == set()  # completed tasks are never overdue
    assert titles(team.manager, open_only=True) == {"ประชุม 100% ทีม", "สรุปยอด"}
    assert titles(team.manager, status="COMPLETED") == {"ส่งใบเสนอราคา"}

    page = team.manager.get(BASE, params={"page_size": 2, "page": 2}).json()
    assert page["total"] == 3
    assert len(page["items"]) == 1


def test_assignable_users_are_scoped(team: Team) -> None:
    def names(client: TestClient) -> set[str]:
        return {u["display_name"] for u in client.get(f"{BASE}/assignable-users").json()}

    assert names(team.alice) == {"alice@example.com"}  # only themself
    assert names(team.manager) == {"manager@example.com", "alice@example.com", "bob@example.com"}
    assert "carol@example.com" in names(team.admin)
    found = team.manager.get(f"{BASE}/assignable-users", params={"q": "bob"}).json()
    assert [u["display_name"] for u in found] == ["bob@example.com"]
    assert set(found[0]) == {"id", "display_name", "job_title", "department"}


# --- Comments ----------------------------------------------------------------------------


def test_comments_notify_and_respect_authorship(team: Team) -> None:
    task = create(team.manager, assignee_ids=[uid(team.alice), uid(team.bob)])
    path = f"{BASE}/{task['id']}/comments"

    created = team.alice.post(path, json={"body": "  ส่งร่างแรกแล้วค่ะ  "})
    assert created.status_code == 201
    comment = created.json()[0]
    assert comment["body"] == "ส่งร่างแรกแล้วค่ะ"
    assert comment["can_edit"] and comment["can_delete"]
    assert notifications_for(team.db, "manager@example.com") == [
        "ความคิดเห็นใหม่ในงาน: เตรียมรายงานยอดขาย"
    ]
    assert notifications_for(team.db, "bob@example.com")[-1].startswith("ความคิดเห็นใหม่")
    assert len(notifications_for(team.db, "alice@example.com")) == 1  # only the assignment

    seen_by_bob = team.bob.get(path).json()[0]
    assert seen_by_bob["can_edit"] is False and seen_by_bob["can_delete"] is False
    one = f"{path}/{comment['id']}"
    assert team.bob.patch(one, json={"body": "แก้"}).status_code == 403
    assert team.bob.delete(one).status_code == 403

    edited = team.alice.patch(one, json={"body": "ส่งร่างที่สองแล้ว"}).json()[0]
    assert edited["edited_at"] is not None
    assert team.alice.post(path, json={"body": "   "}).status_code == 422
    assert team.alice.post(path, json={"body": "x" * 5001}).status_code == 422

    assert team.manager.delete(one).status_code == 204  # managers moderate
    assert team.alice.get(path).json() == []
    assert team.alice.delete(f"{path}/{uuid.uuid4()}").status_code == 404


# --- Attachments ------------------------------------------------------------------------


def test_attachments_upload_download_and_delete(team: Team) -> None:
    task = create(team.manager, assignee_ids=[uid(team.alice)])
    path = f"{BASE}/{task['id']}/attachments"

    uploaded = team.alice.post(
        path, files={"file": ("บันทึกการประชุม.txt", THAI_TEXT.encode(), "text/plain")}
    )
    assert uploaded.status_code == 201, uploaded.text
    item = uploaded.json()[0]
    assert item["file_type"] == "TXT"
    assert item["can_delete"] is True
    key = f"tasks/{task['id']}/{item['id']}"
    assert team.storage.objects[key] == THAI_TEXT.encode()
    assert team.manager.get(f"{BASE}/{task['id']}").json()["attachment_count"] == 1

    download = team.manager.get(f"{path}/{item['id']}/download")
    assert download.status_code == 200
    assert download.content == THAI_TEXT.encode()
    assert "filename*=UTF-8''" in download.headers["content-disposition"]
    assert download.headers["x-content-type-options"] == "nosniff"
    assert team.db.scalar(
        "SELECT count(*) FROM audit_logs WHERE action = 'task.attachment_downloaded'"
    )

    spoofed = team.alice.post(path, files={"file": ("virus.pdf", b"MZ\x90\x00binary", "app/pdf")})
    assert spoofed.status_code in (415, 422)
    assert team.bob.post(path, files={"file": ("a.txt", b"hi", "text/plain")}).status_code == 404

    assert team.alice.delete(f"{path}/{item['id']}").status_code == 204
    assert key not in team.storage.objects
    assert team.alice.get(path).json() == []
    events = [e["event_type"] for e in team.alice.get(f"{BASE}/{task['id']}/history").json()]
    assert "ATTACHMENT_ADDED" in events and "ATTACHMENT_REMOVED" in events


def test_attachment_storage_failure_leaves_no_row(team: Team) -> None:
    task = create(team.alice)
    team.storage.fail_puts = True
    response = team.alice.post(
        f"{BASE}/{task['id']}/attachments", files={"file": ("a.txt", b"hello", "text/plain")}
    )
    assert response.status_code == 503
    assert team.db.scalar("SELECT count(*) FROM task_attachments") == 0


def test_oversized_attachment_is_rejected_before_reading(team: Team) -> None:
    task = create(team.alice)
    response = team.alice.post(
        f"{BASE}/{task['id']}/attachments",
        content=b"x",
        headers={"content-type": "multipart/form-data; boundary=x", "content-length": "999999999"},
    )
    assert response.status_code == 413


# --- Dashboard ----------------------------------------------------------------------------


def test_dashboard_task_summary(team: Team) -> None:
    now = datetime.now(UTC)
    create(team.manager, "เลยกำหนด", assignee_ids=[uid(team.alice)])
    overdue_id = team.alice.get(BASE).json()["items"][0]["id"]
    team.manager.patch(
        f"{BASE}/{overdue_id}", json={"due_at": (now - timedelta(hours=2)).isoformat()}
    )
    create(team.alice, "ใกล้ครบกำหนด", due_at=(now + timedelta(days=2)).isoformat())
    create(team.alice, "ไม่มีกำหนด")
    done = create(team.alice, "เสร็จแล้ว")
    team.alice.post(f"{BASE}/{done['id']}/status", json={"status": "COMPLETED"})
    create(team.manager, "งานของบ็อบ", assignee_ids=[uid(team.bob)])

    tasks = team.alice.get("/api/v1/dashboard/summary").json()["tasks"]
    assert tasks["open_assigned"] == 3
    assert tasks["overdue"] == 1
    assert tasks["due_soon"] == 1
    assert [t["title"] for t in tasks["upcoming"]] == ["เลยกำหนด", "ใกล้ครบกำหนด", "ไม่มีกำหนด"]
    assert tasks["upcoming"][0]["is_overdue"] is True
