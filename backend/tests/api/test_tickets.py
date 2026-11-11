"""IT helpdesk: visibility, status rules, assignment, internal notes, history, notifications."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.conftest import Factory

AsUser = Callable[..., TestClient]
BASE = "/api/v1/tickets"


@dataclass
class Desk:
    db: Factory
    alice: TestClient  # EMPLOYEE
    bob: TestClient  # EMPLOYEE
    it: TestClient  # IT_SUPPORT
    it2: TestClient  # IT_SUPPORT
    manager: TestClient  # MANAGER (no ticket rights beyond his own)


@pytest.fixture
def desk(db: Factory, as_user: AsUser) -> Desk:
    return Desk(
        db=db,
        alice=as_user(["EMPLOYEE"], email="alice@example.com"),
        bob=as_user(["EMPLOYEE"], email="bob@example.com"),
        it=as_user(["IT_SUPPORT"], email="it@example.com"),
        it2=as_user(["IT_SUPPORT"], email="it2@example.com"),
        manager=as_user(["MANAGER"], email="manager@example.com"),
    )


def uid(client: TestClient) -> str:
    return str(client.get("/api/v1/auth/me").json()["user"]["id"])


def create(client: TestClient, **extra: Any) -> dict[str, Any]:
    body = {"title": "เครื่องพิมพ์ชั้น 3 ใช้ไม่ได้", "description": "กระดาษติดทุกครั้ง", **extra}
    response = client.post(BASE, json=body)
    assert response.status_code == 201, response.text
    return dict(response.json())


def notes(client: TestClient) -> list[str]:
    return [n["title"] for n in client.get("/api/v1/notifications").json()["items"]]


def count(db: Factory, sql: str, **params: Any) -> int:
    with db.engine.connect() as conn:
        return int(conn.scalar(text(sql), params) or 0)


def test_requires_authentication_and_permissions(
    new_client: Callable[[], TestClient], as_user: AsUser
) -> None:
    assert new_client().get(BASE).status_code == 401
    nobody = as_user([])
    assert nobody.get(BASE).status_code == 403
    assert nobody.post(BASE, json={"title": "x", "description": "y"}).status_code == 403


def test_create_numbers_notifies_dispatchers_and_audits(desk: Desk) -> None:
    first = create(desk.alice, category="PRINTER", priority="HIGH")
    second = create(desk.bob)
    prefix, year, number = first["ticket_number"].split("-")
    assert prefix == "IT" and len(year) == 4 and len(number) == 6
    assert second["ticket_number"] == f"IT-{year}-{int(number) + 1:06d}"  # sequential
    assert first["status"] == "OPEN"
    assert first["category"] == "PRINTER" and first["priority"] == "HIGH"
    assert first["capabilities"] == {
        "can_manage": False,
        "can_assign": False,
        "can_comment": True,
        "can_comment_internal": False,
        "allowed_statuses": ["CANCELLED"],
    }
    # Every holder of tickets:assign hears about the new ticket.
    assert any("แจ้งปัญหาใหม่" in t for t in notes(desk.it))
    assert any("แจ้งปัญหาใหม่" in t for t in notes(desk.it2))
    assert not any("แจ้งปัญหาใหม่" in t for t in notes(desk.bob))
    assert count(desk.db, "SELECT count(*) FROM audit_logs WHERE action = 'ticket.created'") == 2


def test_requesters_see_only_their_own_tickets(desk: Desk) -> None:
    mine = create(desk.alice)
    theirs = create(desk.bob, title="อีเมลเข้าไม่ได้")
    listed = desk.alice.get(BASE).json()
    assert [t["id"] for t in listed["items"]] == [mine["id"]]
    # Invisible tickets are "not found", whatever the action.
    for method, path, body in [
        ("GET", f"{BASE}/{theirs['id']}", None),
        ("GET", f"{BASE}/{theirs['id']}/comments", None),
        ("GET", f"{BASE}/{theirs['id']}/history", None),
        ("POST", f"{BASE}/{theirs['id']}/comments", {"body": "สวัสดี"}),
        ("POST", f"{BASE}/{theirs['id']}/status", {"status": "CANCELLED"}),
    ]:
        assert desk.alice.request(method, path, json=body).status_code == 404, path
    # Only IT may look beyond their own tickets.
    assert desk.alice.get(BASE, params={"scope": "all"}).status_code == 403
    assert desk.manager.get(BASE, params={"scope": "all"}).status_code == 403
    assert desk.manager.get(f"{BASE}/{mine['id']}").status_code == 404
    assert desk.it.get(BASE, params={"scope": "all"}).json()["total"] == 2
    assert desk.it.get(f"{BASE}/{theirs['id']}").status_code == 200


def test_it_scopes_filters_and_search(desk: Desk) -> None:
    a = create(desk.alice, title="เน็ตหลุดบ่อย", category="NETWORK")
    create(desk.bob, title="ลงโปรแกรมบัญชี", category="SOFTWARE", priority="URGENT")
    assert (
        desk.it.put(f"{BASE}/{a['id']}/assignee", json={"assignee_id": uid(desk.it)}).status_code
        == 200
    )

    def ids(**params: Any) -> list[str]:
        response = desk.it.get(BASE, params=params)
        assert response.status_code == 200, response.text
        return [t["title"] for t in response.json()["items"]]

    assert ids(scope="assigned") == ["เน็ตหลุดบ่อย"]
    assert ids(scope="unassigned") == ["ลงโปรแกรมบัญชี"]
    assert ids(scope="all", category="NETWORK") == ["เน็ตหลุดบ่อย"]
    assert ids(scope="all", q="โปรแกรม") == ["ลงโปรแกรมบัญชี"]
    assert ids(scope="all", sort="priority")[0] == "ลงโปรแกรมบัญชี"
    assert ids(scope="all", status="IN_PROGRESS") == ["เน็ตหลุดบ่อย"]
    assert ids(scope="mine") == []


def test_assignment_rules(desk: Desk) -> None:
    ticket = create(desk.alice)
    path = f"{BASE}/{ticket['id']}/assignee"
    # Employees cannot assign; IT may only assign IT staff (tickets:manage).
    assert desk.alice.put(path, json={"assignee_id": uid(desk.it)}).status_code == 403
    bad = desk.it.put(path, json={"assignee_id": uid(desk.bob)})
    assert bad.status_code == 422
    assert bad.json()["error"]["details"][0]["field"] == "assignee_id"

    assigned = desk.it.put(path, json={"assignee_id": uid(desk.it2)})
    assert assigned.status_code == 200
    body = assigned.json()
    assert body["assignee"]["display_name"] == "it2@example.com"
    assert body["status"] == "IN_PROGRESS"  # picking up an open ticket starts work
    assert any("มอบหมายให้คุณ" in t for t in notes(desk.it2))

    candidates = desk.it.get(f"{BASE}/assignees").json()
    assert {c["display_name"] for c in candidates} >= {"it@example.com", "it2@example.com"}
    assert "bob@example.com" not in {c["display_name"] for c in candidates}
    assert desk.alice.get(f"{BASE}/assignees").status_code == 403

    cleared = desk.it.put(path, json={"assignee_id": None}).json()
    assert cleared["assignee"] is None
    kinds = [e["event_type"] for e in desk.it.get(f"{BASE}/{ticket['id']}/history").json()]
    assert kinds.count("ASSIGNED") == 1 and kinds.count("UNASSIGNED") == 1


def test_status_transitions_by_role(desk: Desk) -> None:
    ticket = create(desk.alice)
    status = f"{BASE}/{ticket['id']}/status"
    # The requester may not resolve their own ticket.
    assert desk.alice.post(status, json={"status": "RESOLVED"}).status_code == 403

    resolved = desk.it.post(status, json={"status": "RESOLVED"}).json()
    assert resolved["status"] == "RESOLVED" and resolved["resolved_at"] is not None
    assert any("สถานะ" in t for t in notes(desk.alice))

    detail = desk.alice.get(f"{BASE}/{ticket['id']}").json()
    assert detail["capabilities"]["allowed_statuses"] == ["CLOSED", "OPEN"]
    reopened = desk.alice.post(status, json={"status": "OPEN"}).json()
    assert reopened["status"] == "OPEN" and reopened["resolved_at"] is None

    cancelled = desk.alice.post(status, json={"status": "CANCELLED"}).json()
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["capabilities"]["allowed_statuses"] == []
    assert desk.alice.post(status, json={"status": "OPEN"}).status_code == 403
    # IT can still move it anywhere.
    assert desk.it.post(status, json={"status": "CLOSED"}).json()["closed_at"] is not None
    assert (
        count(desk.db, "SELECT count(*) FROM audit_logs WHERE action = 'ticket.status_changed'")
        == 4
    )


def test_internal_notes_are_hidden_from_requesters(desk: Desk) -> None:
    ticket = create(desk.alice)
    comments = f"{BASE}/{ticket['id']}/comments"
    assert desk.alice.post(comments, json={"body": "ลับ", "is_internal": True}).status_code == 403
    assert (
        desk.it.post(
            comments, json={"body": "รอเปลี่ยนอะไหล่ (ภายใน)", "is_internal": True}
        ).status_code
        == 201
    )
    assert desk.it.post(comments, json={"body": "กำลังตรวจสอบให้ครับ"}).status_code == 201

    seen_by_requester = [c["body"] for c in desk.alice.get(comments).json()]
    assert seen_by_requester == ["กำลังตรวจสอบให้ครับ"]
    seen_by_it = desk.it.get(comments).json()
    assert [c["is_internal"] for c in seen_by_it] == [True, False]

    history_alice = desk.alice.get(f"{BASE}/{ticket['id']}/history").json()
    assert all(not e["is_internal"] for e in history_alice)
    history_it = desk.it.get(f"{BASE}/{ticket['id']}/history").json()
    assert any(e["is_internal"] for e in history_it)
    # Internal notes never notify the requester; public replies do.
    replies = [t for t in notes(desk.alice) if "ทีมไอทีตอบกลับ" in t]
    assert len(replies) == 1


def test_requester_reply_resumes_waiting_ticket_and_notifies_assignee(desk: Desk) -> None:
    ticket = create(desk.alice)
    tid = ticket["id"]
    desk.it.put(f"{BASE}/{tid}/assignee", json={"assignee_id": uid(desk.it2)})
    desk.it2.post(f"{BASE}/{tid}/status", json={"status": "WAITING_FOR_USER"})
    desk.alice.post(f"{BASE}/{tid}/comments", json={"body": "ลองแล้วยังไม่ได้ครับ"})
    assert desk.alice.get(f"{BASE}/{tid}").json()["status"] == "IN_PROGRESS"
    assert any("ผู้แจ้งตอบกลับ" in t for t in notes(desk.it2))
    assert not any("ผู้แจ้งตอบกลับ" in t for t in notes(desk.it))


def test_update_category_priority_is_it_only(desk: Desk) -> None:
    ticket = create(desk.alice)
    path = f"{BASE}/{ticket['id']}"
    assert desk.alice.patch(path, json={"priority": "URGENT"}).status_code == 403
    updated = desk.it.patch(path, json={"priority": "URGENT", "category": "ACCOUNT_ACCESS"})
    assert updated.status_code == 200
    assert updated.json()["priority"] == "URGENT"
    kinds = {e["event_type"] for e in desk.it.get(f"{path}/history").json()}
    assert {"PRIORITY_CHANGED", "CATEGORY_CHANGED"} <= kinds


@pytest.mark.parametrize(
    "body",
    [
        {"title": "", "description": "x"},
        {"title": "x", "description": ""},
        {"title": "x" * 301, "description": "x"},
        {"title": "x", "description": "x", "category": "COFFEE"},
    ],
)
def test_create_validation(desk: Desk, body: dict[str, Any]) -> None:
    assert desk.alice.post(BASE, json=body).status_code == 422


def test_unknown_ticket_is_404(desk: Desk) -> None:
    assert desk.it.get(f"{BASE}/{uuid.uuid4()}").status_code == 404
