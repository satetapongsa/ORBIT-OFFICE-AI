"""Files and images in chat (ADR-072)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.document_support import MemoryStorage, make_pdf

AsUser = Callable[..., TestClient]
CHAT = "/api/v1/chat"
PNG = bytes([0x89]) + b"PNG" + bytes([13, 10, 26, 10]) + b"\x00\x00\x00\rIHDR" + b"0" * 32


@pytest.fixture
def storage(api_app: FastAPI) -> MemoryStorage:
    memory = MemoryStorage()
    api_app.state.document_storage = memory
    return memory


def uid(client: TestClient) -> str:
    return str(client.get("/api/v1/auth/me").json()["user"]["id"])


def send(client: TestClient, path: str, name: str, data: bytes, body: str | None = None):  # type: ignore[no-untyped-def]
    return client.post(
        f"{CHAT}/{path}/files",
        files={"file": (name, data, "application/octet-stream")},
        data={"body": body} if body is not None else {},
    )


def test_direct_message_files(as_user: AsUser, storage: MemoryStorage) -> None:
    alice, bob, eve = (as_user(["EMPLOYEE"]) for _ in range(3))
    cid = alice.post(f"{CHAT}/conversations", json={"user_id": uid(bob)}).json()["id"]

    photo = send(alice, f"conversations/{cid}", "หน้าจอ.png", PNG)
    assert photo.status_code == 201, photo.text
    att = photo.json()["attachment"]
    assert photo.json()["body"] == ""
    assert (att["original_filename"], att["file_type"], att["is_image"]) == (
        "หน้าจอ.png",
        "PNG",
        True,
    )
    doc = send(alice, f"conversations/{cid}", "สรุป.pdf", make_pdf(), "รายงานเดือนนี้ครับ")
    assert doc.json()["body"] == "รายงานเดือนนี้ครับ"
    assert doc.json()["attachment"]["is_image"] is False
    assert all(k.startswith(f"chat/dm/{cid}/") for k in storage.objects)

    page = bob.get(f"{CHAT}/conversations/{cid}/messages").json()["items"]
    assert [m["attachment"]["file_type"] for m in page] == ["PNG", "PDF"]
    listed = bob.get(f"{CHAT}/conversations").json()
    assert listed["items"][0]["last_message"]["attachment"]["original_filename"] == "สรุป.pdf"
    assert listed["unread_total"] == 2

    download = bob.get(f"{CHAT}/attachments/{att['id']}")
    assert download.status_code == 200 and download.content == PNG
    assert download.headers["content-type"] == "image/png"
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["x-content-type-options"] == "nosniff"
    assert eve.get(f"{CHAT}/attachments/{att['id']}").status_code == 404
    assert send(eve, f"conversations/{cid}", "x.png", PNG).status_code == 404

    # The caption can be edited; the file stays.
    edited = alice.patch(
        f"{CHAT}/conversations/{cid}/messages/{photo.json()['id']}", json={"body": "จอค้าง"}
    ).json()
    assert edited["body"] == "จอค้าง" and edited["attachment"]["id"] == att["id"]


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("fake.png", b"%PDF-1.4 not an image"),
        ("tool.exe", b"MZ\x90\x00binary"),
        ("a.svg", b"<svg/>"),
    ],
)
def test_file_type_is_checked(
    as_user: AsUser, storage: MemoryStorage, name: str, data: bytes
) -> None:
    alice, bob = as_user(["EMPLOYEE"]), as_user(["EMPLOYEE"])
    cid = alice.post(f"{CHAT}/conversations", json={"user_id": uid(bob)}).json()["id"]
    response = send(alice, f"conversations/{cid}", name, data)
    assert response.status_code == 415
    assert storage.objects == {}
    assert bob.get(f"{CHAT}/conversations/{cid}/messages").json()["items"] == []


def test_storage_failure_sends_nothing(as_user: AsUser, storage: MemoryStorage) -> None:
    alice, bob = as_user(["EMPLOYEE"]), as_user(["EMPLOYEE"])
    cid = alice.post(f"{CHAT}/conversations", json={"user_id": uid(bob)}).json()["id"]
    storage.fail_puts = True
    assert send(alice, f"conversations/{cid}", "a.png", PNG).status_code == 503
    assert bob.get(f"{CHAT}/conversations/{cid}/messages").json()["items"] == []


def test_group_files_follow_membership(as_user: AsUser, storage: MemoryStorage) -> None:
    alice, bob, carol = (as_user(["EMPLOYEE"]) for _ in range(3))
    gid = alice.post(
        f"{CHAT}/groups", json={"name": "ทีม", "member_ids": [uid(bob), uid(carol)]}
    ).json()["id"]
    sent = send(bob, f"groups/{gid}", "ผัง.png", PNG, "ดูผังนี้")
    assert sent.status_code == 201, sent.text
    assert sent.json()["sender_name"] and sent.json()["body"] == "ดูผังนี้"
    aid = sent.json()["attachment"]["id"]
    items = carol.get(f"{CHAT}/groups/{gid}/messages").json()["items"]
    assert items[-1]["attachment"]["id"] == aid
    assert carol.get(f"{CHAT}/attachments/{aid}").content == PNG

    alice.delete(f"{CHAT}/groups/{gid}/members/{uid(carol)}")
    assert carol.get(f"{CHAT}/attachments/{aid}").status_code == 404  # removed: no access
    assert send(carol, f"groups/{gid}", "x.png", PNG).status_code == 404
    assert next(iter(storage.objects)).startswith(f"chat/groups/{gid}/")
