"""AI assistant: access, chat history, streaming, tool permissions and confirmation flow."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.services.ai.providers.base import ProviderError
from tests.ai_support import ScriptedProvider, call, events, say
from tests.conftest import Factory, make_settings

AsUser = Callable[..., TestClient]
BASE = "/api/v1/ai"
TASKS = "/api/v1/tasks"


@pytest.fixture
def provider(api_app: FastAPI) -> ScriptedProvider:
    scripted = ScriptedProvider()
    api_app.state.chat_provider = scripted
    return scripted


def new_session(client: TestClient) -> str:
    response = client.post(f"{BASE}/sessions", json={})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def send(client: TestClient, session_id: str, content: str) -> list[tuple[str, dict[str, Any]]]:
    response = client.post(f"{BASE}/sessions/{session_id}/messages", json={"content": content})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    # Proxies must not compress (and so buffer) the stream.
    assert "no-transform" in response.headers["cache-control"]
    return events(response.text)


def names(stream: list[tuple[str, dict[str, Any]]]) -> list[str]:
    return [e for e, _ in stream]


def uid(client: TestClient) -> str:
    return str(client.get("/api/v1/auth/me").json()["user"]["id"])


def count(db: Factory, sql: str, **params: Any) -> int:
    with db.engine.connect() as conn:
        return int(conn.scalar(text(sql), params) or 0)


# --- Access -------------------------------------------------------------------------------


def test_requires_authentication_and_ai_chat(
    new_client: Callable[[], TestClient], as_user: AsUser, provider: ScriptedProvider
) -> None:
    assert new_client().get(f"{BASE}/status").status_code == 401
    nobody = as_user([])
    assert nobody.get(f"{BASE}/status").status_code == 403
    assert nobody.post(f"{BASE}/sessions", json={}).status_code == 403


def test_status_when_disabled_and_send_refused(api_app: FastAPI, as_user: AsUser) -> None:
    api_app.state.chat_provider = None
    client = as_user(["EMPLOYEE"])
    status = client.get(f"{BASE}/status").json()
    assert status == {
        "enabled": False,
        "provider": None,
        "model": None,
        "tools": [],
        "max_message_chars": 4000,
    }
    session_id = new_session(client)  # history still works without a provider
    response = client.post(f"{BASE}/sessions/{session_id}/messages", json={"content": "สวัสดี"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ai_not_configured"


def test_status_lists_tools_by_permission(
    db: Factory, as_user: AsUser, provider: ScriptedProvider
) -> None:
    employee = as_user(["EMPLOYEE"]).get(f"{BASE}/status").json()
    assert employee["enabled"] is True
    tools = {t["name"]: t["requires_confirmation"] for t in employee["tools"]}
    assert tools == {
        "get_my_tasks": False,
        "get_task_details": False,
        "search_documents": False,
        "read_document": False,
        "find_colleagues": False,
        "create_task": True,
        "update_task_status": True,
    }
    # A role with ai:chat but without ai:use_tools gets a tool-less assistant.
    with db.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO roles (code, name, description, is_system) VALUES ('CHAT_ONLY', 'แชตอย่างเดียว', '', false)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO role_permissions (role_id, permission_id) SELECT r.id, p.id"
                " FROM roles r, permissions p WHERE r.code = 'CHAT_ONLY' AND p.code = 'ai:chat'"
            )
        )
    chat_only = as_user(["CHAT_ONLY"])
    assert chat_only.get(f"{BASE}/status").json()["tools"] == []
    provider.turns.append(say("ฉันดูข้อมูลงานของคุณไม่ได้"))
    send(chat_only, new_session(chat_only), "งานของฉันมีอะไรบ้าง")
    assert provider.requests[-1]["tools"] == []
    assert "Tools are not enabled" in provider.requests[-1]["system"]


# --- Sessions -----------------------------------------------------------------------------


def test_sessions_are_private(as_user: AsUser, provider: ScriptedProvider) -> None:
    alice = as_user(["EMPLOYEE"])
    bob = as_user(["EMPLOYEE"])
    session_id = new_session(alice)
    path = f"{BASE}/sessions/{session_id}"
    assert bob.get(path).status_code == 404
    assert bob.patch(path, json={"title": "x"}).status_code == 404
    assert bob.delete(path).status_code == 404
    assert bob.post(f"{path}/messages", json={"content": "hi"}).status_code == 404
    assert bob.get(f"{BASE}/sessions").json()["total"] == 0

    assert alice.patch(path, json={"title": "วางแผนงาน"}).json()["title"] == "วางแผนงาน"
    assert alice.delete(path).status_code == 204
    assert alice.get(path).status_code == 404
    assert alice.get(f"{BASE}/sessions").json()["total"] == 0


def test_message_validation(as_user: AsUser, provider: ScriptedProvider) -> None:
    client = as_user(["EMPLOYEE"])
    session_id = new_session(client)
    path = f"{BASE}/sessions/{session_id}/messages"
    assert client.post(path, json={"content": "   "}).status_code == 422
    assert client.post(path, json={"content": "ก" * 4001}).status_code == 422
    assert (
        client.post(f"{BASE}/sessions/{uuid.uuid4()}/messages", json={"content": "x"}).status_code
        == 404
    )


# --- Streaming chat -------------------------------------------------------------------------


def test_streams_answer_and_keeps_history(as_user: AsUser, provider: ScriptedProvider) -> None:
    client = as_user(["EMPLOYEE"], email="somchai@example.com")
    session_id = new_session(client)
    provider.turns += [say("สวัสดีครับ มีอะไรให้ช่วยไหม"), say("คุณถามว่าสวัสดีครับ")]

    first = send(client, session_id, "สวัสดีครับ ช่วยวางแผนงานสัปดาห์นี้หน่อย")
    assert names(first) == ["start", "delta", "delta", "done"]
    assert "".join(d["text"] for e, d in first if e == "delta") == "สวัสดีครับ มีอะไรให้ช่วยไหม"
    assert first[0][1]["title"] == "สวัสดีครับ ช่วยวางแผนงานสัปดาห์นี้หน่อย"  # auto title
    assert "somchai@example.com" in provider.requests[0]["system"]

    send(client, session_id, "เมื่อกี้ฉันถามว่าอะไร")
    history = [(m.role, m.content) for m in provider.requests[1]["messages"]]
    assert history == [
        ("user", "สวัสดีครับ ช่วยวางแผนงานสัปดาห์นี้หน่อย"),
        ("assistant", "สวัสดีครับ มีอะไรให้ช่วยไหม"),
        ("user", "เมื่อกี้ฉันถามว่าอะไร"),
    ]
    detail = client.get(f"{BASE}/sessions/{session_id}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "user", "assistant"]
    sessions = client.get(f"{BASE}/sessions").json()
    assert sessions["items"][0]["id"] == session_id


def test_provider_error_is_reported_safely(
    as_user: AsUser, provider: ScriptedProvider, db: Factory
) -> None:
    client = as_user(["EMPLOYEE"])
    session_id = new_session(client)
    provider.error = ProviderError("ผู้ให้บริการ AI ไม่ตอบสนองในขณะนี้", retryable=True)
    stream = send(client, session_id, "สวัสดี")
    assert names(stream) == ["start", "error"]
    assert stream[1][1] == {"code": "ai_provider_error", "message": "ผู้ให้บริการ AI ไม่ตอบสนองในขณะนี้"}
    # The question is kept; no half answer is stored.
    roles = [m["role"] for m in client.get(f"{BASE}/sessions/{session_id}").json()["messages"]]
    assert roles == ["user"]


def test_refusal_and_step_limit(
    api_app: FastAPI, as_user: AsUser, provider: ScriptedProvider
) -> None:
    client = as_user(["EMPLOYEE"])
    session_id = new_session(client)
    provider.turns.append(say("", refused=True))
    assert send(client, session_id, "x")[-1] == (
        "error",
        {"code": "ai_refused", "message": "ผู้ช่วย AI ไม่สามารถตอบคำขอนี้ได้"},
    )
    api_app.state.settings = make_settings(ai_chat_max_tool_steps=2)
    provider.turns += [call("get_my_tasks", {}, "c1"), call("get_my_tasks", {}, "c2")]
    stream = send(client, session_id, "วนไปเรื่อยๆ")
    assert names(stream) == ["start", "tool", "tool", "error"]
    assert stream[-1][1]["code"] == "ai_too_many_steps"


def test_rate_limit(api_app: FastAPI, as_user: AsUser, provider: ScriptedProvider) -> None:
    api_app.state.settings = make_settings(ai_chat_rate_limit_messages=1)
    client = as_user(["EMPLOYEE"])
    session_id = new_session(client)
    provider.turns.append(say("ตอบ"))
    send(client, session_id, "หนึ่ง")
    response = client.post(f"{BASE}/sessions/{session_id}/messages", json={"content": "สอง"})
    assert response.status_code == 429
    assert response.headers["retry-after"]


# --- Tools run as the user --------------------------------------------------------------------


@pytest.fixture
def sales(db: Factory) -> uuid.UUID:
    return db.department("SALES", "ฝ่ายขาย")


def test_read_tool_returns_only_what_the_user_may_see(
    db: Factory, as_user: AsUser, provider: ScriptedProvider, sales: uuid.UUID
) -> None:
    manager = as_user(["MANAGER"], department_id=sales)
    alice = as_user(["EMPLOYEE"], email="alice@example.com", department_id=sales)
    bob = as_user(["EMPLOYEE"], email="bob@example.com", department_id=sales)
    manager.post(TASKS, json={"title": "งานของอลิซ", "assignee_ids": [uid(alice)]})
    secret = manager.post(TASKS, json={"title": "งานลับของบ็อบ", "assignee_ids": [uid(bob)]}).json()

    session_id = new_session(alice)
    provider.turns += [
        call("get_my_tasks", {"scope": "all"}),
        call("get_task_details", {"task_id": secret["id"]}, "call_2"),
        say("คุณมีงาน 1 งาน"),
    ]
    stream = send(alice, session_id, "งานของฉันมีอะไรบ้าง")
    assert names(stream) == ["start", "tool", "tool", "delta", "delta", "done"]
    tools = [d for e, d in stream if e == "tool"]
    assert [t["label"] for t in tools] == ["ค้นหางานของคุณ", "เปิดดูรายละเอียดงาน"]
    assert [t["ok"] for t in tools] == [True, False]

    results = provider.tool_results()
    assert [t["title"] for t in results[0]["data"]["tasks"]] == ["งานของอลิซ"]
    # Someone else's task is "not found" — the model never sees its title.
    assert results[1]["ok"] is False
    assert "งานลับของบ็อบ" not in str(results)
    assert provider.requests[0]["tools"] == [
        "get_my_tasks",
        "get_task_details",
        "search_documents",
        "read_document",
        "find_colleagues",
        "create_task",
        "update_task_status",
    ]
    # The UI never receives raw tool data.
    detail = alice.get(f"{BASE}/sessions/{session_id}").json()
    tool_messages = [m for m in detail["messages"] if m["role"] == "tool"]
    assert all(m["content"] == "" for m in tool_messages)


def test_bad_tool_calls_are_answered_with_errors(
    as_user: AsUser, provider: ScriptedProvider
) -> None:
    client = as_user(["EMPLOYEE"])
    session_id = new_session(client)
    provider.turns += [
        call("run_sql", {"query": "DROP TABLE users"}, "a"),
        call("get_my_tasks", None, "b"),
        call("get_my_tasks", {"limit": 500, "extra": True}, "c"),
        say("ขออภัย"),
    ]
    send(client, session_id, "ลองเครื่องมือแปลกๆ")
    errors = [r["error"] for r in provider.tool_results()]
    assert "unknown or unavailable tool 'run_sql'" in errors[0]
    assert errors[1] == "arguments were not a JSON object"
    assert "limit" in errors[2] and "extra" in errors[2]


# --- Proposed actions need confirmation ------------------------------------------------------


def propose_task(
    client: TestClient, provider: ScriptedProvider, **args: Any
) -> tuple[str, dict[str, Any]]:
    session_id = new_session(client)
    provider.turns += [
        call(
            "create_task",
            {
                "title": "สรุปยอดขายเดือนพฤศจิกายน",
                "priority": "HIGH",
                "due_date": "2026-11-30",
                **args,
            },
        ),
        say("เตรียมงานไว้แล้ว กรุณากดยืนยัน"),
    ]
    stream = send(client, session_id, "สร้างงานสรุปยอดขายให้หน่อย")
    actions = [d for e, d in stream if e == "action"]
    assert len(actions) == 1
    return session_id, actions[0]


def test_create_task_only_after_confirmation(
    db: Factory, as_user: AsUser, provider: ScriptedProvider, sales: uuid.UUID
) -> None:
    client = as_user(["EMPLOYEE"], department_id=sales)
    session_id, action = propose_task(client, provider)
    assert action["status"] == "PENDING"
    assert action["summary"] == (
        "สร้างงาน “สรุปยอดขายเดือนพฤศจิกายน” · ความสำคัญสูง · กำหนดส่ง 2026-11-30 · ผู้รับผิดชอบ: คุณเอง"
    )
    pending = provider.tool_results()[0]
    assert pending["status"] == "awaiting_user_confirmation"
    assert count(db, "SELECT count(*) FROM tasks") == 0  # nothing ran yet

    confirmed = client.post(f"{BASE}/actions/{action['id']}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    body = confirmed.json()
    assert body["status"] == "EXECUTED"
    task = client.get(body["result"]["link"].replace("/tasks", TASKS)).json()
    assert task["title"] == "สรุปยอดขายเดือนพฤศจิกายน"
    assert task["created_by"]["id"] == uid(client)  # acted as the user
    assert task["due_at"].startswith("2026-11-30T16:59")  # 23:59 Bangkok
    assert count(db, "SELECT count(*) FROM audit_logs WHERE action = 'ai.action_confirmed'") == 1
    assert count(db, "SELECT count(*) FROM audit_logs WHERE action = 'task.created'") == 1

    again = client.post(f"{BASE}/actions/{action['id']}/confirm")
    assert again.status_code == 409
    assert count(db, "SELECT count(*) FROM tasks") == 1  # never twice

    # The model learns the outcome through a system note on the next turn.
    provider.turns.append(say("สร้างงานเรียบร้อยแล้ว"))
    send(client, session_id, "สร้างแล้วใช่ไหม")
    notes = [m.content for m in provider.requests[-1]["messages"] if m.role == "system"]
    assert len(notes) == 1 and "ดำเนินการสำเร็จ" in notes[0]
    assert notes[0].endswith(body["result"]["link"])  # readable, no raw JSON
    detail = client.get(f"{BASE}/sessions/{session_id}").json()
    assert detail["actions"][0]["status"] == "EXECUTED"


def test_reject_and_ownership(db: Factory, as_user: AsUser, provider: ScriptedProvider) -> None:
    client = as_user(["EMPLOYEE"])
    other = as_user(["ADMIN"])
    _, action = propose_task(client, provider)
    assert other.post(f"{BASE}/actions/{action['id']}/confirm").status_code == 404
    assert other.post(f"{BASE}/actions/{action['id']}/reject").status_code == 404

    rejected = client.post(f"{BASE}/actions/{action['id']}/reject").json()
    assert rejected["status"] == "REJECTED"
    assert client.post(f"{BASE}/actions/{action['id']}/confirm").status_code == 409
    assert count(db, "SELECT count(*) FROM tasks") == 0
    assert count(db, "SELECT count(*) FROM audit_logs WHERE action = 'ai.action_rejected'") == 1


def test_expired_action_cannot_run(
    db: Factory, as_user: AsUser, provider: ScriptedProvider
) -> None:
    client = as_user(["EMPLOYEE"])
    _, action = propose_task(client, provider)
    with db.engine.begin() as conn:
        conn.execute(text("UPDATE ai_action_requests SET expires_at = now() - interval '1 minute'"))
    response = client.post(f"{BASE}/actions/{action['id']}/confirm")
    assert response.status_code == 409
    assert count(db, "SELECT count(*) FROM ai_action_requests WHERE status = 'EXPIRED'") == 1
    assert count(db, "SELECT count(*) FROM tasks") == 0


def test_employee_cannot_propose_assigning_others(
    as_user: AsUser, provider: ScriptedProvider, sales: uuid.UUID
) -> None:
    client = as_user(["EMPLOYEE"], department_id=sales)
    colleague = as_user(["EMPLOYEE"], department_id=sales)
    session_id = new_session(client)
    provider.turns += [
        call("create_task", {"title": "งาน", "assignee_ids": [uid(colleague)]}),
        say("ทำไม่ได้"),
    ]
    stream = send(client, session_id, "มอบงานให้เพื่อน")
    assert "action" not in names(stream)
    assert provider.tool_results()[0] == {
        "ok": False,
        "error": "คุณไม่มีสิทธิ์ใช้ความสามารถนี้",
        "details": [],
    }


def test_confirmation_rechecks_permissions(
    db: Factory, as_user: AsUser, provider: ScriptedProvider, sales: uuid.UUID
) -> None:
    manager = as_user(["MANAGER"], department_id=sales)
    alice = as_user(["EMPLOYEE"], department_id=sales)
    bob = as_user(["EMPLOYEE"], department_id=sales)
    task = manager.post(TASKS, json={"title": "ติดตามลูกค้า", "assignee_ids": [uid(alice)]}).json()

    session_id = new_session(alice)
    provider.turns += [
        call("update_task_status", {"task_id": task["id"], "status": "COMPLETED"}),
        say("กรุณายืนยัน"),
    ]
    action = next(d for e, d in send(alice, session_id, "งานนี้เสร็จแล้ว") if e == "action")
    assert action["summary"] == "เปลี่ยนสถานะงาน “ติดตามลูกค้า” จากรอดำเนินการ เป็นเสร็จสิ้น"

    # Before Alice confirms, the manager reassigns the task: she can no longer see it.
    manager.put(f"{TASKS}/{task['id']}/assignees", json={"user_ids": [uid(bob)]})
    result = alice.post(f"{BASE}/actions/{action['id']}/confirm").json()
    assert result["status"] == "FAILED"
    assert result["error"] == "ไม่พบงาน หรือคุณไม่มีสิทธิ์เข้าถึง"
    assert manager.get(f"{TASKS}/{task['id']}").json()["status"] == "TODO"


def test_assignee_cannot_propose_cancel(
    as_user: AsUser, provider: ScriptedProvider, sales: uuid.UUID
) -> None:
    manager = as_user(["MANAGER"], department_id=sales)
    alice = as_user(["EMPLOYEE"], department_id=sales)
    task = manager.post(TASKS, json={"title": "งาน", "assignee_ids": [uid(alice)]}).json()
    session_id = new_session(alice)
    provider.turns += [
        call("update_task_status", {"task_id": task["id"], "status": "CANCELLED"}),
        say("ไม่ได้"),
    ]
    stream = send(alice, session_id, "ยกเลิกงานนี้")
    assert "action" not in names(stream)
    assert provider.tool_results()[0]["ok"] is False
