"""Direct messages between employees and personal notes with AI summary (ADR-060)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.ai.providers.base import ProviderError
from tests.ai_support import ScriptedProvider, say
from tests.conftest import Factory

AsUser = Callable[..., TestClient]
CHAT = "/api/v1/chat"
NOTES = "/api/v1/notes"


def uid(client: TestClient) -> str:
    return str(client.get("/api/v1/auth/me").json()["user"]["id"])


def open_chat(client: TestClient, other: TestClient) -> str:
    response = client.post(f"{CHAT}/conversations", json={"user_id": uid(other)})
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


# --- Chat -------------------------------------------------------------------------------


def test_two_employees_chat_and_unread_counts(as_user: AsUser) -> None:
    alice, bob = as_user(["EMPLOYEE"]), as_user(["EMPLOYEE"])
    cid = open_chat(alice, bob)
    assert open_chat(bob, alice) == cid  # one thread per pair, whoever opens it

    sent = alice.post(f"{CHAT}/conversations/{cid}/messages", json={"body": "  สวัสดีครับ  "})
    assert sent.status_code == 201, sent.text
    assert sent.json()["body"] == "สวัสดีครับ"
    alice.post(f"{CHAT}/conversations/{cid}/messages", json={"body": "ประชุมบ่ายสองนะ"})

    assert alice.get(f"{CHAT}/unread-count").json() == {"unread_total": 0}  # own messages
    assert bob.get(f"{CHAT}/unread-count").json() == {"unread_total": 2}
    listed = bob.get(f"{CHAT}/conversations").json()
    assert listed["unread_total"] == 2
    item = listed["items"][0]
    assert item["unread_count"] == 2
    assert item["other"]["id"] == uid(alice)
    assert item["last_message"]["body"] == "ประชุมบ่ายสองนะ"

    page = bob.get(f"{CHAT}/conversations/{cid}/messages").json()
    assert [m["body"] for m in page["items"]] == ["สวัสดีครับ", "ประชุมบ่ายสองนะ"]
    assert page["has_more"] is False
    assert bob.post(f"{CHAT}/conversations/{cid}/read").json() == {"unread_total": 0}

    bob.post(f"{CHAT}/conversations/{cid}/messages", json={"body": "รับทราบ"})
    assert alice.get(f"{CHAT}/unread-count").json() == {"unread_total": 1}


def test_history_is_paged_with_before(as_user: AsUser) -> None:
    alice, bob = as_user(["EMPLOYEE"]), as_user(["EMPLOYEE"])
    cid = open_chat(alice, bob)
    for i in range(5):
        alice.post(f"{CHAT}/conversations/{cid}/messages", json={"body": f"m{i}"})
    newest = alice.get(f"{CHAT}/conversations/{cid}/messages", params={"limit": 2}).json()
    assert [m["body"] for m in newest["items"]] == ["m3", "m4"] and newest["has_more"] is True
    older = alice.get(
        f"{CHAT}/conversations/{cid}/messages",
        params={"limit": 2, "before": newest["items"][0]["id"]},
    ).json()
    assert [m["body"] for m in older["items"]] == ["m1", "m2"] and older["has_more"] is True


def test_outsiders_and_admins_cannot_read_a_conversation(as_user: AsUser) -> None:
    alice, bob = as_user(["EMPLOYEE"]), as_user(["EMPLOYEE"])
    admin = as_user(["ADMIN"])
    cid = open_chat(alice, bob)
    alice.post(f"{CHAT}/conversations/{cid}/messages", json={"body": "ความลับ"})
    for path in ("", "/messages"):
        assert admin.get(f"{CHAT}/conversations/{cid}{path}").status_code == 404
    assert admin.post(f"{CHAT}/conversations/{cid}/messages", json={"body": "x"}).status_code == 404
    assert admin.post(f"{CHAT}/conversations/{cid}/read").status_code == 404
    assert admin.get(f"{CHAT}/conversations").json()["items"] == []


def test_rules_for_starting_and_sending(as_user: AsUser, db: Factory) -> None:
    alice, bob = as_user(["EMPLOYEE"]), as_user(["EMPLOYEE"])
    me = alice.post(f"{CHAT}/conversations", json={"user_id": uid(alice)})
    assert me.status_code == 422
    unknown = alice.post(
        f"{CHAT}/conversations", json={"user_id": "00000000-0000-0000-0000-000000000001"}
    )
    assert unknown.status_code == 404
    empty = alice.post(
        f"{CHAT}/conversations/{open_chat(alice, bob)}/messages", json={"body": "   "}
    )
    assert empty.status_code == 422
    too_long = alice.post(
        f"{CHAT}/conversations/{open_chat(alice, bob)}/messages", json={"body": "ก" * 4001}
    )
    assert too_long.status_code == 422

    cid = open_chat(alice, bob)
    with db.engine.begin() as conn:
        from sqlalchemy import text

        conn.execute(text("UPDATE users SET is_active = false WHERE id = :u"), {"u": uid(bob)})
    blocked = alice.post(f"{CHAT}/conversations/{cid}/messages", json={"body": "อยู่ไหม"})
    assert blocked.status_code == 409
    assert alice.get(f"{CHAT}/conversations/{cid}/messages").status_code == 200  # history stays


def test_chat_needs_the_permission(as_user: AsUser) -> None:
    nobody = as_user([])
    assert nobody.get(f"{CHAT}/conversations").status_code == 403
    alice = as_user(["EMPLOYEE"])
    refused = alice.post(f"{CHAT}/conversations", json={"user_id": uid(nobody)})
    assert refused.status_code == 409  # cannot open a thread the other side cannot read


# --- Notes ------------------------------------------------------------------------------


def test_notes_crud_and_privacy(as_user: AsUser) -> None:
    owner, other, admin = as_user(["EMPLOYEE"]), as_user(["EMPLOYEE"]), as_user(["ADMIN"])
    created = owner.post(NOTES, json={"title": " ประชุมทีม ", "content": "เตรียมสไลด์\nส่งรายงาน"})
    assert created.status_code == 201, created.text
    note = created.json()
    assert note["title"] == "ประชุมทีม" and note["ai_summary"] is None
    owner.post(NOTES, json={"title": "ซื้อของ", "content": "กาแฟ"})

    listed = owner.get(NOTES).json()
    assert [n["title"] for n in listed] == ["ซื้อของ", "ประชุมทีม"]
    assert listed[1]["preview"] == "เตรียมสไลด์ ส่งรายงาน"
    assert [n["title"] for n in owner.get(NOTES, params={"q": "สไลด์"}).json()] == ["ประชุมทีม"]
    assert owner.get(NOTES, params={"q": "%"}).json() == []  # % is literal

    edited = owner.patch(f"{NOTES}/{note['id']}", json={"content": "เตรียมสไลด์ให้เสร็จ"})
    assert edited.json()["content"] == "เตรียมสไลด์ให้เสร็จ"

    for intruder in (other, admin):
        assert intruder.get(f"{NOTES}/{note['id']}").status_code == 404
        assert intruder.patch(f"{NOTES}/{note['id']}", json={"title": "x"}).status_code == 404
        assert intruder.delete(f"{NOTES}/{note['id']}").status_code == 404
        assert intruder.get(NOTES).json() == []

    assert owner.delete(f"{NOTES}/{note['id']}").status_code == 204
    assert owner.get(f"{NOTES}/{note['id']}").status_code == 404
    assert owner.post(NOTES, json={"title": "", "content": ""}).status_code == 422
    assert owner.post(NOTES, json={"title": "ยาว", "content": "ก" * 20001}).status_code == 422


def test_note_ai_summary_is_stored_and_marked_outdated(as_user: AsUser, api_app: FastAPI) -> None:
    provider = ScriptedProvider()
    api_app.state.chat_provider = provider
    owner = as_user(["EMPLOYEE"])
    note = owner.post(NOTES, json={"title": "งานสัปดาห์นี้", "content": "ส่งรายงานวันศุกร์"}).json()

    provider.turns.append(say("สรุป: ต้องส่งรายงานวันศุกร์"))
    done = owner.post(f"{NOTES}/{note['id']}/summary")
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["ai_summary"] == "สรุป: ต้องส่งรายงานวันศุกร์"
    assert body["summary_outdated"] is False
    sent = provider.requests[-1]
    assert sent["tools"] == []
    assert "ส่งรายงานวันศุกร์" in sent["messages"][0].content
    assert owner.get(NOTES).json()[0]["has_summary"] is True

    changed = owner.patch(f"{NOTES}/{note['id']}", json={"content": "ส่งรายงานวันพฤหัส"}).json()
    assert changed["ai_summary"] == "สรุป: ต้องส่งรายงานวันศุกร์"
    assert changed["summary_outdated"] is True


def test_note_summary_errors(as_user: AsUser, api_app: FastAPI) -> None:
    owner = as_user(["EMPLOYEE"])
    empty = owner.post(NOTES, json={"title": "ว่าง"}).json()
    full = owner.post(NOTES, json={"title": "มีข้อความ", "content": "ข้อความ"}).json()
    api_app.state.chat_provider = None
    assert owner.post(f"{NOTES}/{full['id']}/summary").status_code == 503
    provider = ScriptedProvider(error=ProviderError("ผู้ให้บริการ AI ไม่ตอบสนองในขณะนี้"))
    api_app.state.chat_provider = provider
    assert owner.post(f"{NOTES}/{empty['id']}/summary").status_code == 422
    failed = owner.post(f"{NOTES}/{full['id']}/summary")
    assert failed.status_code == 503
    assert owner.get(f"{NOTES}/{full['id']}").json()["ai_summary"] is None


def test_notes_need_the_permission(as_user: AsUser) -> None:
    assert as_user([]).get(NOTES).status_code == 403


def test_read_receipts_and_typing_indicator(as_user: AsUser, db: Factory) -> None:
    alice, bob = as_user(["EMPLOYEE"]), as_user(["EMPLOYEE"])
    cid = open_chat(alice, bob)
    sent = alice.post(f"{CHAT}/conversations/{cid}/messages", json={"body": "ถึงไหนแล้ว"}).json()

    page = alice.get(f"{CHAT}/conversations/{cid}/messages").json()
    assert page["other_last_read_at"] is None  # Bob has not opened it yet
    assert page["other_typing"] is False

    bob.post(f"{CHAT}/conversations/{cid}/read")
    seen = alice.get(f"{CHAT}/conversations/{cid}/messages").json()["other_last_read_at"]
    assert seen is not None and seen >= sent["created_at"]  # "อ่านแล้ว"
    item = alice.get(f"{CHAT}/conversations").json()["items"][0]
    assert item["other_last_read_at"] == seen

    assert bob.post(f"{CHAT}/conversations/{cid}/typing").status_code == 204
    assert alice.get(f"{CHAT}/conversations/{cid}/messages").json()["other_typing"] is True
    assert alice.get(f"{CHAT}/conversations").json()["items"][0]["other_typing"] is True
    assert bob.get(f"{CHAT}/conversations/{cid}/messages").json()["other_typing"] is False

    # An old signal expires on its own...
    from sqlalchemy import text

    with db.engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE conversations SET low_typing_at = now() - interval '10 seconds',"
                " high_typing_at = now() - interval '10 seconds'"
            )
        )
    assert alice.get(f"{CHAT}/conversations/{cid}/messages").json()["other_typing"] is False
    # ...and sending a message ends it at once.
    bob.post(f"{CHAT}/conversations/{cid}/typing")
    bob.post(f"{CHAT}/conversations/{cid}/messages", json={"body": "ใกล้เสร็จแล้ว"})
    assert alice.get(f"{CHAT}/conversations/{cid}/messages").json()["other_typing"] is False

    outsider = as_user(["EMPLOYEE"])
    assert outsider.post(f"{CHAT}/conversations/{cid}/typing").status_code == 404
