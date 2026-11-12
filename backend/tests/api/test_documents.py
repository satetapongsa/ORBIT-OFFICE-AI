"""Document Center: upload, validation, access control, versions, ACL, processing, history."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.main import create_app
from tests.conftest import BACKEND_OPTIONS, Factory, make_settings
from tests.document_support import (
    THAI_TEXT,
    InlineProcessor,
    MemoryStorage,
    make_broken_docx,
    make_docx,
    make_pdf,
    make_xlsx,
    make_zip_bomb,
)

AsUser = Callable[..., TestClient]
BASE = "/api/v1/documents"


@dataclass
class Env:
    storage: MemoryStorage
    processor: InlineProcessor
    db: Factory


@pytest.fixture
def env(api_app: FastAPI, db: Factory, test_engine: Engine) -> Env:
    storage = MemoryStorage()
    processor = InlineProcessor(test_engine, storage)
    api_app.state.document_storage = storage
    api_app.state.document_processor = processor
    return Env(storage, processor, db)


def upload(
    client: TestClient,
    *,
    name: str = "นโยบายการลา.txt",
    data: bytes = THAI_TEXT.encode(),
    title: str = "นโยบายการลา",
    **fields: Any,
) -> Any:
    form = {"title": title, **{k: str(v) for k, v in fields.items()}}
    return client.post(BASE, data=form, files={"file": (name, data, "application/octet-stream")})


def created(client: TestClient, **kwargs: Any) -> dict[str, Any]:
    response = upload(client, **kwargs)
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def user_id(client: TestClient) -> str:
    return str(client.get("/api/v1/auth/me").json()["user"]["id"])


# --- Upload and processing ----------------------------------------------------------------


def test_upload_stores_file_and_extracts_text(env: Env, as_user: AsUser) -> None:
    sales = env.db.department("SALES")
    client = as_user(["EMPLOYEE"], department_id=sales)
    body = created(client, category="POLICY", visibility="DEPARTMENT")

    assert body["category"] == "POLICY"
    assert body["visibility"] == "DEPARTMENT"
    assert body["department"]["code"] == "SALES"  # defaults to the uploader's department
    assert body["access_level"] == "MANAGE"  # the owner
    version = body["current_version"]
    assert version["version_number"] == 1
    assert version["file_type"] == "TXT"
    assert version["processing_status"] == "READY"
    assert body["versions"][0]["original_filename"] == "นโยบายการลา.txt"
    assert body["versions"][0]["char_count"] == len(THAI_TEXT)

    key = f"documents/{body['id']}/{version['id']}"  # server-generated key
    assert env.storage.objects[key] == THAI_TEXT.encode()

    preview = client.get(f"{BASE}/{body['id']}/text").json()
    assert preview["content"] == THAI_TEXT
    assert preview["truncated"] is False
    assert (
        env.db.scalar(
            "SELECT count(*) FROM audit_logs WHERE action = 'document.uploaded' AND entity_id = :i",
            i=body["id"],
        )
        == 1
    )


@pytest.mark.parametrize(
    ("name", "factory", "expected_type", "snippet"),
    [
        ("policy.pdf", make_pdf, "PDF", "ORBIT leave policy 2026"),
        ("handbook.docx", make_docx, "DOCX", "บทที่ 1 การเข้างาน"),
        ("budget.xlsx", make_xlsx, "XLSX", "คอมพิวเตอร์\t12"),
        ("thai-windows.txt", lambda: THAI_TEXT.encode("cp874"), "TXT", "พนักงานลาได้"),
    ],
)
def test_supported_formats_are_extracted(
    env: Env,
    as_user: AsUser,
    name: str,
    factory: Callable[[], bytes],
    expected_type: str,
    snippet: str,
) -> None:
    client = as_user(["EMPLOYEE"])
    body = created(client, name=name, data=factory())
    assert body["current_version"]["file_type"] == expected_type
    assert body["current_version"]["processing_status"] == "READY"
    assert snippet in client.get(f"{BASE}/{body['id']}/text").json()["content"]
    if expected_type == "PDF":
        assert body["versions"][0]["page_count"] == 1


@pytest.mark.parametrize(
    ("name", "data", "status", "code"),
    [
        ("tool.exe", b"MZ\x90\x00binary", 415, "unsupported_file_type"),
        ("fake.txt", b"MZ\x90\x00\x00\x00binary\x00\x01\x02", 415, "unsupported_file_type"),
        ("report.txt", make_pdf(), 415, "unsupported_file_type"),  # content says PDF
        ("report.docx", make_pdf(), 415, "unsupported_file_type"),
        ("sheet.xlsx", make_docx(), 415, "unsupported_file_type"),  # DOCX renamed
        ("empty.txt", b"", 422, "empty_file"),
        ("bomb.docx", make_zip_bomb(), 422, "unsafe_file"),
    ],
)
def test_rejects_unsupported_or_unsafe_files(
    env: Env, as_user: AsUser, name: str, data: bytes, status: int, code: str
) -> None:
    response = upload(as_user(["EMPLOYEE"]), name=name, data=data)
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
    assert env.storage.objects == {}  # nothing stored
    assert env.db.scalar("SELECT count(*) FROM documents") == 0


def test_upload_permissions_and_authentication(env: Env, as_user: AsUser, new_client: Any) -> None:
    assert upload(new_client()).status_code == 401
    assert upload(as_user([])).status_code == 403  # no documents:upload


def test_upload_department_rules(env: Env, as_user: AsUser) -> None:
    sales = env.db.department("SALES")
    hr = env.db.department("HR")
    employee = as_user(["EMPLOYEE"], department_id=sales)
    other = upload(employee, department_id=hr)
    assert other.status_code == 403  # only your own department
    nodept = upload(as_user(["EMPLOYEE"]), visibility="DEPARTMENT")
    assert nodept.status_code == 422
    admin = as_user(["ADMIN"])  # documents:manage may file anywhere
    assert created(admin, department_id=hr, visibility="DEPARTMENT")["department"]["code"] == "HR"


def test_file_too_large(env: Env, db: Factory, test_engine: Engine) -> None:
    from tests.conftest import login

    app = create_app(make_settings(upload_max_bytes=2_000))
    storage = MemoryStorage()
    app.state.document_storage = storage
    app.state.document_processor = InlineProcessor(test_engine, storage)
    from app.core.rate_limit import InMemoryRateLimiter

    app.state.rate_limiter = InMemoryRateLimiter()
    db.user("big@example.com")
    with TestClient(app, raise_server_exceptions=False, backend_options=BACKEND_OPTIONS) as client:
        login(client, "big@example.com")
        # Within the multipart allowance: the service measures the real size.
        measured = upload(client, data=b"a" * 5_000)
        assert measured.status_code == 413
        assert measured.json()["error"]["code"] == "file_too_large"
        # Far above the limit: rejected from Content-Length before the body is read.
        early = client.post(
            BASE,
            content=b"x",
            headers={
                "Content-Type": "multipart/form-data; boundary=x",
                "Content-Length": "9999999",
            },
        )
        assert early.status_code == 413
    assert storage.objects == {}


def test_storage_failure_is_reported_and_nothing_is_saved(env: Env, as_user: AsUser) -> None:
    env.storage.fail_puts = True
    response = upload(as_user(["EMPLOYEE"]))
    assert response.status_code == 503
    assert env.db.scalar("SELECT count(*) FROM documents") == 0


def test_failed_processing_is_visible_notified_and_retryable(env: Env, as_user: AsUser) -> None:
    client = as_user(["EMPLOYEE"])
    body = created(client, name="broken.docx", data=make_broken_docx())
    version = body["versions"][0]
    assert version["processing_status"] == "FAILED"
    assert version["processing_error"] == "ไฟล์ DOCX เสียหายหรืออ่านไม่ได้"
    assert client.get(f"{BASE}/{body['id']}/text").status_code == 409

    notes = client.get("/api/v1/notifications").json()["items"]
    assert notes[0]["type"] == "DOCUMENT"
    assert notes[0]["link_url"] == f"/documents/{body['id']}"

    retry = client.post(f"{BASE}/{body['id']}/versions/{version['id']}/reprocess")
    assert retry.status_code == 202
    assert env.processor.queued[-1] == (uuid.UUID(version["id"]), True)

    ok = created(client)
    ready = ok["versions"][0]["id"]
    assert client.post(f"{BASE}/{ok['id']}/versions/{ready}/reprocess").status_code == 409


def test_queued_version_stays_pending(env: Env, as_user: AsUser) -> None:
    env.processor.run = False  # broker accepted the job, worker has not run yet
    client = as_user(["EMPLOYEE"])
    body = created(client)
    assert body["current_version"]["processing_status"] == "PENDING"
    assert client.get(f"{BASE}/{body['id']}/text").status_code == 409
    env.processor.process(uuid.UUID(body["current_version"]["id"]))
    detail = client.get(f"{BASE}/{body['id']}").json()
    assert detail["current_version"]["processing_status"] == "READY"


# --- Access control -----------------------------------------------------------------------


@dataclass
class People:
    owner: TestClient
    colleague: TestClient  # same department
    outsider: TestClient  # other department
    admin: TestClient


@pytest.fixture
def people(env: Env, as_user: AsUser) -> People:
    sales = env.db.department("SALES")
    hr = env.db.department("HR")
    return People(
        owner=as_user(["EMPLOYEE"], department_id=sales),
        colleague=as_user(["EMPLOYEE"], department_id=sales),
        outsider=as_user(["EMPLOYEE"], department_id=hr),
        admin=as_user(["ADMIN"], department_id=hr),
    )


def _can_read(client: TestClient, doc_id: str) -> bool:
    detail = client.get(f"{BASE}/{doc_id}").status_code
    download = client.get(f"{BASE}/{doc_id}/download").status_code
    preview = client.get(f"{BASE}/{doc_id}/text").status_code
    listed = any(d["id"] == doc_id for d in client.get(BASE).json()["items"])
    results = {detail == 200, download == 200, preview == 200, listed}
    assert len(results) == 1, (detail, download, preview, listed)  # every path agrees
    if detail != 200:
        assert {detail, download, preview} == {404}  # existence is not revealed
    return results.pop()


def test_visibility_levels_apply_to_every_read_path(env: Env, people: People) -> None:
    doc = created(people.owner, visibility="PRIVATE")["id"]
    assert [_can_read(c, doc) for c in (people.colleague, people.outsider, people.admin)] == [
        False,
        False,
        True,  # documents:manage override
    ]

    patch = people.owner.patch(f"{BASE}/{doc}", json={"visibility": "DEPARTMENT"})
    assert patch.status_code == 200
    assert [_can_read(c, doc) for c in (people.colleague, people.outsider)] == [True, False]

    people.owner.patch(f"{BASE}/{doc}", json={"visibility": "COMPANY"})
    assert [_can_read(c, doc) for c in (people.colleague, people.outsider)] == [True, True]


def test_explicit_grants_and_their_levels(env: Env, people: People) -> None:
    doc = created(people.owner, visibility="PRIVATE")["id"]
    outsider_id = user_id(people.outsider)

    def grant(level: str) -> Any:
        return people.owner.put(
            f"{BASE}/{doc}/acl",
            json={
                "entries": [
                    {"principal_type": "USER", "principal_id": outsider_id, "access_level": level}
                ]
            },
        )

    assert grant("VIEW").status_code == 200
    assert _can_read(people.outsider, doc)
    assert people.outsider.patch(f"{BASE}/{doc}", json={"title": "x"}).status_code == 403
    assert people.outsider.get(f"{BASE}/{doc}/acl").status_code == 403
    assert people.outsider.get(f"{BASE}/{doc}/history").status_code == 403
    caps = people.outsider.get(f"{BASE}/{doc}").json()["capabilities"]
    assert caps == {
        "can_edit": False,
        "can_manage": False,
        "can_delete": False,
        "can_manage_access": False,
        "can_upload_version": False,
        "can_view_history": False,
    }
    note = people.outsider.get("/api/v1/notifications").json()["items"][0]
    assert note["title"] == "มีการแชร์เอกสารให้คุณ: นโยบายการลา"

    assert grant("EDIT").status_code == 200
    assert people.outsider.patch(f"{BASE}/{doc}", json={"title": "ฉบับแก้ไข"}).status_code == 200
    assert people.outsider.patch(f"{BASE}/{doc}", json={"visibility": "COMPANY"}).status_code == 403
    new_version = people.outsider.post(
        f"{BASE}/{doc}/versions", files={"file": ("v2.txt", b"version two", "text/plain")}
    )
    assert new_version.status_code == 201
    assert people.outsider.put(f"{BASE}/{doc}/acl", json={"entries": []}).status_code == 403

    assert grant("MANAGE").status_code == 200
    assert people.outsider.get(f"{BASE}/{doc}/acl").status_code == 200
    assert people.outsider.delete(f"{BASE}/{doc}").status_code == 403  # no documents:delete

    # Department and role grants work too; removing grants revokes access immediately.
    sales_dept = people.owner.get(f"{BASE}/{doc}").json()["department"]["id"]
    replace = people.owner.put(
        f"{BASE}/{doc}/acl",
        json={
            "entries": [
                {"principal_type": "DEPARTMENT", "principal_id": sales_dept, "access_level": "VIEW"}
            ]
        },
    )
    assert replace.status_code == 200
    assert replace.json()["entries"][0]["principal_name"] == "SALES"
    assert not _can_read(people.outsider, doc)
    assert _can_read(people.colleague, doc)


def test_acl_validation(env: Env, people: People) -> None:
    doc = created(people.owner)["id"]
    me = user_id(people.owner)
    other = user_id(people.outsider)
    entry = {"principal_type": "USER", "principal_id": other, "access_level": "VIEW"}
    for entries in (
        [entry, entry],  # duplicate
        [{**entry, "principal_id": me}],  # the owner
        [{**entry, "principal_id": str(uuid.uuid4())}],  # unknown user
        [{**entry, "principal_type": "ROLE", "principal_id": str(uuid.uuid4())}],
    ):
        response = people.owner.put(f"{BASE}/{doc}/acl", json={"entries": entries})
        assert response.status_code == 422, entries
    role = str(env.db.role_id("HR"))
    ok = people.owner.put(
        f"{BASE}/{doc}/acl",
        json={
            "entries": [{"principal_type": "ROLE", "principal_id": role, "access_level": "VIEW"}]
        },
    )
    assert ok.status_code == 200
    assert ok.json()["entries"][0]["principal_name"] == "ฝ่ายบุคคล"


def test_download_headers_versions_and_audit(env: Env, people: People) -> None:
    body = created(people.owner, name="แผนงาน ปี 69.txt", data=b"version one")
    doc = body["id"]
    first = body["versions"][0]["id"]
    response = people.owner.get(f"{BASE}/{doc}/download")
    assert response.status_code == 200
    assert response.content == b"version one"
    assert response.headers["x-content-type-options"] == "nosniff"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert "filename*=UTF-8''%E0%B9%81%E0%B8%9C" in disposition  # Thai name, percent-encoded
    assert response.headers["content-type"].startswith("text/plain")

    v2 = people.owner.post(
        f"{BASE}/{doc}/versions", files={"file": ("plan.txt", b"version two", "text/plain")}
    )
    detail = v2.json()
    assert detail["current_version"]["version_number"] == 2
    assert [v["version_number"] for v in detail["versions"]] == [2, 1]
    assert people.owner.get(f"{BASE}/{doc}/download").content == b"version two"
    old = people.owner.get(f"{BASE}/{doc}/download", params={"version_id": first})
    assert old.content == b"version one"
    assert people.owner.get(f"{BASE}/{doc}/text").json()["content"] == "version two"
    assert (
        env.db.scalar(
            "SELECT count(*) FROM audit_logs WHERE action = 'document.downloaded' AND entity_id = :i",
            i=doc,
        )
        == 3
    )
    # A version id from another document is not accepted.
    other = created(people.owner)["versions"][0]["id"]
    assert (
        people.owner.get(f"{BASE}/{doc}/download", params={"version_id": other}).status_code == 404
    )


def test_delete_requires_permission_and_hides_document(env: Env, people: People) -> None:
    doc = created(people.owner, visibility="COMPANY")["id"]
    assert people.owner.delete(f"{BASE}/{doc}").status_code == 403  # owners archive instead
    archived = people.owner.patch(f"{BASE}/{doc}", json={"status": "ARCHIVED"})
    assert archived.json()["status"] == "ARCHIVED"
    assert people.admin.delete(f"{BASE}/{doc}").status_code == 204
    for client in (people.owner, people.colleague, people.admin):
        assert client.get(f"{BASE}/{doc}").status_code == 404
        assert client.get(BASE).json()["total"] == 0
    assert env.db.scalar("SELECT deleted_at IS NOT NULL FROM documents WHERE id = :i", i=doc)


def test_list_search_filters_and_paging(env: Env, people: People) -> None:
    created(people.owner, title="คู่มือ 100% ใหม่", category="MANUAL", visibility="COMPANY")
    created(people.owner, title="แบบฟอร์มลา", category="FORM", visibility="COMPANY")
    created(people.colleague, title="รายงานยอดขาย", category="REPORT", visibility="COMPANY")

    def titles(client: TestClient, **params: Any) -> list[str]:
        return [d["title"] for d in client.get(BASE, params=params).json()["items"]]

    assert titles(people.outsider, q="100%") == ["คู่มือ 100% ใหม่"]  # % is literal
    assert titles(people.outsider, q="_") == []
    assert titles(people.outsider, category="FORM") == ["แบบฟอร์มลา"]
    assert sorted(titles(people.owner, mine="true")) == ["คู่มือ 100% ใหม่", "แบบฟอร์มลา"]
    assert titles(people.outsider, sort="title", page_size=1, page=1) == ["คู่มือ 100% ใหม่"]
    page = people.outsider.get(BASE, params={"page_size": 2}).json()
    assert page["total"] == 3
    assert len(page["items"]) == 2
    assert titles(people.outsider, processing_status="FAILED") == []


def test_history_visible_to_managers_and_auditors(env: Env, people: People) -> None:
    doc = created(people.owner, visibility="COMPANY")["id"]
    people.owner.patch(f"{BASE}/{doc}", json={"title": "ชื่อใหม่"})
    people.colleague.get(f"{BASE}/{doc}/download")
    history = people.owner.get(f"{BASE}/{doc}/history").json()
    assert [h["action"] for h in history] == [
        "document.downloaded",
        "document.updated",
        "document.uploaded",
    ]
    assert history[1]["details"] == {"fields": ["title"]}
    assert people.colleague.get(f"{BASE}/{doc}/history").status_code == 403
    assert people.admin.get(f"{BASE}/{doc}/history").status_code == 200


def test_directory_search_exposes_safe_fields_only(env: Env, as_user: AsUser, db: Factory) -> None:
    db.user("somchai@example.com")
    with db.engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET display_name = 'สมชาย ใจดี' WHERE email = 'somchai@example.com'")
        )
    employee = as_user(["EMPLOYEE"])
    results = employee.get("/api/v1/directory/users", params={"q": "สมชาย"}).json()
    assert [r["display_name"] for r in results] == ["สมชาย ใจดี"]
    assert set(results[0]) == {"id", "display_name", "job_title", "department"}
    assert as_user([]).get("/api/v1/directory/users").status_code == 403
