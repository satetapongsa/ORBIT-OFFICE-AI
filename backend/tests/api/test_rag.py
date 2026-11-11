"""RAG: indexing, content search and the assistant's document tools.

The central property: a passage from a document the user may not read never appears in a
search result or in anything sent to the model (docs/SECURITY.md §5).
"""

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
from sqlalchemy.orm import Session

from app.services.documents.indexing import NO_TEXT, index_version
from tests.ai_support import ScriptedProvider, call, events, say
from tests.conftest import Factory, make_settings
from tests.document_support import HashEmbedder, InlineProcessor, MemoryStorage, make_pdf

AsUser = Callable[..., TestClient]
DOCS = "/api/v1/documents"
AI = "/api/v1/ai"

LEAVE = "นโยบายการลาพักร้อน พนักงานประจำมีสิทธิ์ลาพักร้อนได้ปีละ 10 วันทำการ ต้องแจ้งล่วงหน้า 7 วัน"
SALARY = "ความลับ: โครงสร้างเงินเดือนผู้บริหาร ปรับขึ้นร้อยละ 12 ในปี 2570 รหัสโครงการ PHOENIX-77"
SECURITY = "มาตรฐานรหัสผ่าน รหัสผ่านต้องยาวอย่างน้อย 12 ตัวอักษร และเปลี่ยนทุก 90 วัน"


@dataclass
class Env:
    app: FastAPI
    db: Factory
    engine: Engine
    storage: MemoryStorage
    processor: InlineProcessor


@pytest.fixture
def env(api_app: FastAPI, db: Factory, test_engine: Engine) -> Env:
    storage = MemoryStorage()
    processor = InlineProcessor(test_engine, storage)
    api_app.state.document_storage = storage
    api_app.state.document_processor = processor
    api_app.state.embedding_provider = None
    return Env(api_app, db, test_engine, storage, processor)


def use_embeddings(env: Env, embedder: HashEmbedder | None = None) -> HashEmbedder:
    embedder = embedder or HashEmbedder()
    env.processor.embedder = embedder
    env.app.state.embedding_provider = embedder
    return embedder


def upload(client: TestClient, title: str, body: str, **fields: Any) -> dict[str, Any]:
    response = client.post(
        DOCS,
        data={"title": title, **{k: str(v) for k, v in fields.items()}},
        files={"file": (f"{title}.txt", body.encode(), "text/plain")},
    )
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def search(client: TestClient, q: str) -> dict[str, Any]:
    response = client.get(f"{DOCS}/search", params={"q": q})
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def titles(client: TestClient, q: str) -> list[str]:
    return [r["title"] for r in search(client, q)["results"]]


def uid(client: TestClient) -> str:
    return str(client.get("/api/v1/auth/me").json()["user"]["id"])


# --- Indexing -----------------------------------------------------------------------------


def test_upload_is_indexed_and_searchable_by_keyword(env: Env, as_user: AsUser) -> None:
    client = as_user(["EMPLOYEE"])
    doc = upload(client, "นโยบายการลา", LEAVE, visibility="COMPANY")
    version = doc["versions"][0]
    assert version["index_status"] == "READY"
    assert version["chunk_count"] == 1
    assert env.db.scalar("SELECT count(*) FROM document_chunks WHERE embedding IS NULL") == 1

    result = search(client, "ลาพักร้อน")
    assert result["mode"] == "keyword"
    assert result["degraded"] is False
    hit = result["results"][0]
    assert hit["title"] == "นโยบายการลา"
    assert hit["document_id"] == doc["id"]
    assert "10 วันทำการ" in hit["snippet"]
    assert search(client, "งบประมาณการตลาดไตรมาสสาม")["results"] == []


def test_semantic_index_and_hybrid_search(env: Env, as_user: AsUser) -> None:
    embedder = use_embeddings(env)
    client = as_user(["EMPLOYEE"])
    upload(client, "นโยบายการลา", LEAVE, visibility="COMPANY")
    upload(client, "มาตรฐานรหัสผ่าน", SECURITY, visibility="COMPANY")
    assert (
        env.db.scalar(
            "SELECT count(*) FROM document_chunks WHERE embedding IS NOT NULL AND embedding_model = :m",
            m=embedder.model,
        )
        == 2
    )

    result = search(client, "ลาพักร้อนได้กี่วัน")
    assert result["mode"] == "hybrid"
    assert result["results"][0]["title"] == "นโยบายการลา"
    assert titles(client, "รหัสผ่านยาวกี่ตัวอักษร")[0] == "มาตรฐานรหัสผ่าน"


def test_embedding_failures_fall_back_to_keyword(env: Env, as_user: AsUser) -> None:
    embedder = use_embeddings(env, HashEmbedder(fail=True))
    client = as_user(["EMPLOYEE"])
    doc = upload(client, "นโยบายการลา", LEAVE, visibility="COMPANY")
    version = doc["versions"][0]
    assert version["index_status"] == "FAILED"  # chunks kept, vectors missing
    assert "ค้นหาด้วยคำได้" in version["index_error"]
    result = search(client, "ลาพักร้อน")
    assert result["mode"] == "keyword"
    assert result["degraded"] is True
    assert result["results"][0]["title"] == "นโยบายการลา"

    # Re-indexing after the provider recovers fills in the vectors.
    embedder.fail = False
    with Session(env.engine) as session:
        status = index_version(
            session, make_settings(), embedder, uuid.UUID(version["id"]), force=True
        )
    assert status == "READY"
    assert search(client, "ลาพักร้อน")["mode"] == "hybrid"


def test_version_without_text_is_skipped(env: Env, as_user: AsUser) -> None:
    client = as_user(["EMPLOYEE"])
    doc = upload(client, "เอกสาร", "ข้อความชั่วคราว")
    version_id = uuid.UUID(doc["versions"][0]["id"])
    with env.engine.begin() as conn:
        conn.execute(
            text("UPDATE document_version_texts SET content = '' WHERE document_version_id = :v"),
            {"v": version_id},
        )
    with Session(env.engine) as session:
        assert index_version(session, make_settings(), None, version_id, force=True) == "SKIPPED"
    detail = client.get(f"{DOCS}/{doc['id']}").json()["versions"][0]
    assert detail["index_status"] == "SKIPPED" and detail["index_error"] == NO_TEXT
    assert env.db.scalar("SELECT count(*) FROM document_chunks") == 0


def test_pdf_pages_are_kept_apart(env: Env, as_user: AsUser) -> None:
    client = as_user(["EMPLOYEE"])
    response = client.post(
        DOCS,
        data={"title": "Handbook"},
        files={
            "file": (
                "handbook.pdf",
                make_pdf("Chapter one onboarding", "Chapter two security"),
                "application/pdf",
            )
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["versions"][0]["page_count"] == 2
    preview = client.get(f"{DOCS}/{body['id']}/text").json()["content"]
    assert "\f" not in preview and "Chapter two security" in preview


# --- Permission isolation -------------------------------------------------------------------


def test_search_only_returns_accessible_documents(env: Env, as_user: AsUser, db: Factory) -> None:
    use_embeddings(env)
    finance = db.department("FIN", "ฝ่ายการเงิน")
    sales = db.department("SALES", "ฝ่ายขาย")
    owner = as_user(["EMPLOYEE"], email="owner@example.com", department_id=finance)
    colleague = as_user(["EMPLOYEE"], email="colleague@example.com", department_id=finance)
    outsider = as_user(["EMPLOYEE"], email="outsider@example.com", department_id=sales)
    admin = as_user(["ADMIN"])

    secret = upload(owner, "เงินเดือนผู้บริหาร", SALARY, visibility="PRIVATE")
    team = upload(owner, "นโยบายการลาฝ่ายการเงิน", LEAVE, visibility="DEPARTMENT")

    for client in (colleague, outsider):
        assert titles(client, "โครงสร้างเงินเดือนผู้บริหาร") == []
        assert titles(client, "PHOENIX-77") == []
    assert titles(owner, "PHOENIX-77") == ["เงินเดือนผู้บริหาร"]
    assert titles(admin, "PHOENIX-77") == ["เงินเดือนผู้บริหาร"]  # documents:manage override
    assert titles(colleague, "ลาพักร้อน") == ["นโยบายการลาฝ่ายการเงิน"]
    assert titles(outsider, "ลาพักร้อน") == []

    # Granting access takes effect immediately (no re-index): the ACL is applied at query time.
    acl = owner.put(
        f"{DOCS}/{secret['id']}/acl",
        json={
            "entries": [
                {"principal_type": "USER", "principal_id": uid(outsider), "access_level": "VIEW"}
            ]
        },
    )
    assert acl.status_code == 200, acl.text
    assert titles(outsider, "PHOENIX-77") == ["เงินเดือนผู้บริหาร"]
    owner.put(f"{DOCS}/{secret['id']}/acl", json={"entries": []})
    assert titles(outsider, "PHOENIX-77") == []

    # Deleted documents disappear from search for everyone.
    assert admin.delete(f"{DOCS}/{team['id']}").status_code == 204
    assert titles(colleague, "ลาพักร้อน") == []
    assert titles(owner, "ลาพักร้อน") == []


def test_only_the_current_version_is_searched(env: Env, as_user: AsUser) -> None:
    client = as_user(["EMPLOYEE"])
    doc = upload(client, "ประกาศ", "ประกาศเดิม ปิดสำนักงานวันที่ 5 ธันวาคม", visibility="COMPANY")
    response = client.post(
        f"{DOCS}/{doc['id']}/versions",
        files={"file": ("ประกาศ.txt", "ประกาศใหม่ ปิดสำนักงานวันที่ 12 ธันวาคม".encode(), "text/plain")},
    )
    assert response.status_code == 201
    snippets = [r["snippet"] for r in search(client, "ปิดสำนักงาน")["results"]]
    assert snippets == ["ประกาศใหม่ ปิดสำนักงานวันที่ 12 ธันวาคม"]
    assert (
        env.db.scalar(
            "SELECT count(DISTINCT document_version_id) FROM document_chunks WHERE document_id = :d",
            d=doc["id"],
        )
        == 1
    )


def test_search_requires_documents_read(
    env: Env, as_user: AsUser, new_client: Callable[[], TestClient]
) -> None:
    assert new_client().get(f"{DOCS}/search", params={"q": "x"}).status_code == 401
    assert as_user([]).get(f"{DOCS}/search", params={"q": "x"}).status_code == 403
    client = as_user(["EMPLOYEE"])
    assert client.get(f"{DOCS}/search", params={"q": ""}).status_code == 422
    assert client.get(f"{DOCS}/search", params={"q": "%_%"}).json()["results"] == []


# --- Assistant ------------------------------------------------------------------------------


@pytest.fixture
def provider(env: Env) -> ScriptedProvider:
    scripted = ScriptedProvider()
    env.app.state.chat_provider = scripted
    return scripted


def ask(client: TestClient, content: str) -> list[tuple[str, dict[str, Any]]]:
    session_id = client.post(f"{AI}/sessions", json={}).json()["id"]
    response = client.post(f"{AI}/sessions/{session_id}/messages", json={"content": content})
    assert response.status_code == 200, response.text
    return events(response.text)


def test_assistant_answers_from_permitted_passages_with_citations(
    env: Env, as_user: AsUser, provider: ScriptedProvider, db: Factory
) -> None:
    use_embeddings(env)
    finance = db.department("FIN", "ฝ่ายการเงิน")
    owner = as_user(["EMPLOYEE"], department_id=finance)
    reader = as_user(["EMPLOYEE"], department_id=finance)
    upload(owner, "เงินเดือนผู้บริหาร", SALARY, visibility="PRIVATE")
    leave = upload(owner, "นโยบายการลา", LEAVE, visibility="DEPARTMENT")

    provider.turns += [
        call("search_documents", {"query": "ลาพักร้อนได้กี่วัน และเงินเดือนผู้บริหาร PHOENIX-77"}),
        say("พนักงานประจำลาพักร้อนได้ปีละ 10 วันทำการ [1]"),
    ]
    stream = ask(reader, "ลาพักร้อนได้กี่วัน")

    sent = str(provider.requests[-1]["messages"])
    assert "PHOENIX-77" not in provider.tool_results()[0].__repr__().replace('PHOENIX-77"', "")
    assert "โครงสร้างเงินเดือนผู้บริหาร" not in sent  # the private passage never reached the model
    result = provider.tool_results()[0]["data"]
    assert [r["title"] for r in result["results"]] == ["นโยบายการลา"]
    assert result["results"][0]["source"] == 1
    assert "cite" in result["instructions"]
    assert "search_documents" in provider.requests[0]["system"]

    done = next(d for e, d in stream if e == "done")
    assert done["citations"] == [
        {
            "n": 1,
            "document_id": leave["id"],
            "version_id": leave["current_version"]["id"],
            "chunk_id": done["citations"][0]["chunk_id"],
            "title": "นโยบายการลา",
            "page": None,
        }
    ]
    session = reader.get(f"{AI}/sessions").json()["items"][0]["id"]
    stored = reader.get(f"{AI}/sessions/{session}").json()["messages"][-1]
    assert stored["citations"] == [
        {"n": 1, "document_id": leave["id"], "title": "นโยบายการลา", "page": None}
    ]


def test_no_evidence_is_reported(env: Env, as_user: AsUser, provider: ScriptedProvider) -> None:
    client = as_user(["EMPLOYEE"])
    upload(client, "นโยบายการลา", LEAVE, visibility="COMPANY")
    provider.turns += [
        call("search_documents", {"query": "นโยบายการเบิกค่าเดินทางต่างประเทศ"}),
        say("ไม่พบข้อมูลในเอกสารที่คุณเข้าถึงได้"),
    ]
    stream = ask(client, "เบิกค่าเดินทางต่างประเทศได้เท่าไร")
    result = provider.tool_results()[0]["data"]
    assert result["results"] == []
    assert "no evidence" in result["note"]
    assert next(d for e, d in stream if e == "done")["citations"] == []


def test_read_document_respects_access(
    env: Env, as_user: AsUser, provider: ScriptedProvider
) -> None:
    owner = as_user(["EMPLOYEE"])
    other = as_user(["EMPLOYEE"])
    secret = upload(owner, "เงินเดือนผู้บริหาร", SALARY, visibility="PRIVATE")
    provider.turns += [call("read_document", {"document_id": secret["id"]}), say("ไม่พบเอกสาร")]
    ask(other, "สรุปเอกสารนี้ให้หน่อย")
    result = provider.tool_results()[0]
    assert result["ok"] is False
    assert "PHOENIX" not in str(provider.requests[-1]["messages"])

    provider.turns += [call("read_document", {"document_id": secret["id"]}), say("สรุป [1]")]
    ask(owner, "สรุปเอกสารนี้ให้หน่อย")
    read = provider.tool_results()[0]["data"]
    assert read["title"] == "เงินเดือนผู้บริหาร"
    assert read["text"] == SALARY and read["truncated"] is False and read["source"] == 1


def test_document_tools_need_documents_read(
    env: Env, as_user: AsUser, provider: ScriptedProvider, db: Factory
) -> None:
    with db.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO roles (code, name, description, is_system) VALUES ('AI_TASKS', 'AI งาน', '', false)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO role_permissions (role_id, permission_id) SELECT r.id, p.id FROM roles r,"
                " permissions p WHERE r.code = 'AI_TASKS' AND p.code IN ('ai:chat', 'ai:use_tools', 'tasks:read_own')"
            )
        )
    client = as_user(["AI_TASKS"])
    names = {t["name"] for t in client.get(f"{AI}/status").json()["tools"]}
    assert "search_documents" not in names and "read_document" not in names
    provider.turns += [call("search_documents", {"query": "ลา"}), say("ค้นไม่ได้")]
    ask(client, "หาเอกสารการลา")
    assert "unknown or unavailable tool" in provider.tool_results()[0]["error"]
    assert "cannot search company documents" in provider.requests[0]["system"]
