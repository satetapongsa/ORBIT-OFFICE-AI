"""Group chats (ADR-071)."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.conftest import Factory

AsUser = Callable[..., TestClient]
API = "/api/v1/chat/groups"


def uid(client: TestClient) -> str:
    return str(client.get("/api/v1/auth/me").json()["user"]["id"])


def version(client: TestClient, since: int = -1) -> int:
    return int(
        client.get("/api/v1/chat/events", params={"since": since, "wait": 0}).json()["version"]
    )


def test_group_lifecycle(as_user: AsUser) -> None:
    alice, bob, carol, dave, outsider = (as_user(["EMPLOYEE"]) for _ in range(5))
    created = alice.post(API, json={"name": "ทีมขาย", "member_ids": [uid(bob), uid(carol)]})
    assert created.status_code == 201, created.text
    group = created.json()
    gid = group["id"]
    assert group["member_count"] == 3 and group["my_role"] == "ADMIN"
    assert group["members"][0]["role"] == "ADMIN"
    assert outsider.get(f"{API}/{gid}").status_code == 404

    b0 = version(bob)
    sent = alice.post(f"{API}/{gid}/messages", json={"body": "สวัสดีทุกคน"})
    assert sent.status_code == 201 and sent.json()["sender_name"]
    assert version(bob, b0) != b0  # real-time wake-up for members

    listed = bob.get(API).json()[0]
    assert listed["unread_count"] == 2  # the "created" system message and the greeting
    assert bob.get("/api/v1/chat/unread-count").json()["unread_total"] == 2
    page = bob.get(f"{API}/{gid}/messages").json()
    assert [(m["kind"], m["body"]) for m in page["items"]][-1] == ("TEXT", "สวัสดีทุกคน")
    assert page["items"][0]["kind"] == "SYSTEM"
    bob.post(f"{API}/{gid}/read")
    assert bob.get("/api/v1/chat/unread-count").json()["unread_total"] == 0
    reads = {
        r["display_name"]: r["last_read_at"]
        for r in alice.get(f"{API}/{gid}/messages").json()["reads"]
    }
    assert sum(1 for v in reads.values() if v) == 1  # bob has read; carol has not

    bob.post(f"{API}/{gid}/typing")
    assert alice.get(f"{API}/{gid}/messages").json()["typing_names"] != []
    assert alice.get(API).json()[0]["typing_names"] != []

    mid = sent.json()["id"]
    assert bob.patch(f"{API}/{gid}/messages/{mid}", json={"body": "x"}).status_code == 403
    edited = alice.patch(f"{API}/{gid}/messages/{mid}", json={"body": "สวัสดีครับทุกคน"}).json()
    assert edited["edited_at"] is not None

    # Admin actions.
    assert bob.patch(f"{API}/{gid}", json={"name": "x"}).status_code == 403
    assert (
        alice.patch(f"{API}/{gid}", json={"name": "ทีมขายภาคเหนือ"}).json()["name"] == "ทีมขายภาคเหนือ"
    )
    added = alice.post(f"{API}/{gid}/members", json={"user_ids": [uid(dave)]})
    assert added.json()["member_count"] == 4
    # Notices about my own actions are not "new" to me.
    assert alice.get("/api/v1/chat/unread-count").json()["unread_total"] == 0
    assert dave.get(API).json()[0]["unread_count"] >= 1
    assert bob.delete(f"{API}/{gid}/members/{uid(carol)}").status_code == 403
    assert alice.delete(f"{API}/{gid}/members/{uid(carol)}").status_code == 204
    assert carol.get(f"{API}/{gid}/messages").status_code == 404  # removed: no access
    assert bob.delete(f"{API}/{gid}/members/{uid(bob)}").status_code == 204  # leave
    bodies = [
        m["body"]
        for m in dave.get(f"{API}/{gid}/messages").json()["items"]
        if m["kind"] == "SYSTEM"
    ]
    assert any("เปลี่ยนชื่อกลุ่ม" in b for b in bodies)
    assert any("ออกจากกลุ่ม" in b for b in bodies)

    # The last admin leaves: the longest-standing member takes over.
    alice.delete(f"{API}/{gid}/members/{uid(alice)}")
    assert dave.get(f"{API}/{gid}").json()["my_role"] == "ADMIN"
    dave.delete(f"{API}/{gid}/members/{uid(dave)}")
    assert dave.get(API).json() == []


def test_department_group_and_validation(as_user: AsUser, db: Factory) -> None:
    sales, it = db.department("SALES"), db.department("IT")
    lead = as_user(["EMPLOYEE"], department_id=sales)
    as_user(["EMPLOYEE"], department_id=sales)
    as_user(["EMPLOYEE"], department_id=sales)
    as_user(["EMPLOYEE"], department_id=it)
    room = lead.post(API, json={"name": "ห้องฝ่ายขาย", "include_department_id": str(sales)})
    assert room.status_code == 201 and room.json()["member_count"] == 3
    assert lead.post(API, json={"name": "x", "include_department_id": str(it)}).status_code == 403
    assert lead.post(API, json={"name": "ว่าง", "member_ids": []}).status_code == 422
    nobody = as_user([])
    refused = lead.post(API, json={"name": "x", "member_ids": [uid(nobody)]})
    assert refused.status_code == 422  # cannot use chat
    assert lead.post(API, json={"name": "", "member_ids": [uid(lead)]}).status_code == 422
