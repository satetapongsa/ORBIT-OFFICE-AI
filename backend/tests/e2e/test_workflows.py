"""End-to-end workflows over real HTTP against a running stack (Phase 9).

Requests go through the public entry point (Next.js proxy or Nginx), the real API, PostgreSQL,
Redis, MinIO and the Celery worker. Uses the development seed accounts; writes data prefixed
"E2E" and removes what the API allows (tickets stay, cancelled). Run with::

    bash scripts/e2e-test.sh            # inside the backend container, via http://frontend:3000

Never point it at production.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Iterator
from typing import Any

import httpx2 as httpx
import pytest

BASE_URL = os.environ.get("ORBIT_E2E_BASE_URL", "")
PASSWORD = os.environ.get("SEED_DEV_PASSWORD", "")
DOMAIN = os.environ.get("ORBIT_E2E_DOMAIN", "orbit.example.com")

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not BASE_URL or not PASSWORD,
        reason="set ORBIT_E2E_BASE_URL and SEED_DEV_PASSWORD (see scripts/e2e-test.sh)",
    ),
]

RUN = uuid.uuid4().hex[:8]  # unique marker so concurrent or repeated runs never collide


class Api:
    """A signed-in browser-like client (cookies + CSRF header)."""

    def __init__(self, email: str) -> None:
        self.client = httpx.Client(base_url=BASE_URL, timeout=60)
        response = self.client.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
        assert response.status_code == 200, f"{email}: {response.status_code} {response.text}"
        self.me: dict[str, Any] = response.json()

    def _headers(self) -> dict[str, str]:
        token = self.client.cookies.get("orbit_csrf")
        return {"X-CSRF-Token": token} if token else {}

    def get(self, path: str, **kw: Any) -> httpx.Response:
        return self.client.get(f"/api/v1{path}", **kw)

    def send(self, method: str, path: str, **kw: Any) -> httpx.Response:
        return self.client.request(method, f"/api/v1{path}", headers=self._headers(), **kw)

    def ok(self, method: str, path: str, expected: int = 200, **kw: Any) -> Any:
        response = self.get(path, **kw) if method == "GET" else self.send(method, path, **kw)
        assert response.status_code == expected, f"{method} {path}: {response.text}"
        return response.json() if response.content else None


@pytest.fixture(scope="module")
def people() -> Iterator[dict[str, Api]]:
    clients = {role: Api(f"{role}@{DOMAIN}") for role in ("admin", "manager", "it", "employee")}
    yield clients
    for api in clients.values():
        api.send("POST", "/auth/logout")
        api.client.close()


def test_unauthenticated_requests_are_refused() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=30) as anonymous:
        assert anonymous.get("/api/v1/tasks").status_code == 401
        assert anonymous.get("/api/v1/health/live").status_code == 200
        page = anonymous.get("/login")
        assert page.status_code == 200
        assert "frame-ancestors 'none'" in page.headers["content-security-policy"]


def test_task_lifecycle(people: dict[str, Api]) -> None:
    employee = people["employee"]
    task = employee.ok(
        "POST", "/tasks", 201, json={"title": f"E2E {RUN} ตรวจรายงาน", "priority": "HIGH"}
    )
    assert task["assignees"][0]["id"] == employee.me["user"]["id"]
    for status in ("IN_PROGRESS", "COMPLETED"):
        task = employee.ok("POST", f"/tasks/{task['id']}/status", json={"status": status})
    assert task["status"] == "COMPLETED" and task["completed_at"]
    # Another department cannot see it.
    assert people["it"].get(f"/tasks/{task['id']}").status_code == 404
    employee.ok("DELETE", f"/tasks/{task['id']}", 204)


def test_document_upload_processing_search_and_isolation(people: dict[str, Api]) -> None:
    employee, it = people["employee"], people["it"]
    marker = uuid.uuid4().hex  # random: shares no trigrams with earlier runs
    body = f"นโยบายทดสอบ {marker}\nเอกสารนี้สร้างโดยชุดทดสอบแบบครบวงจร".encode()
    document = employee.ok(
        "POST",
        "/documents",
        201,
        data={"title": f"E2E {RUN} เอกสาร", "visibility": "PRIVATE"},
        files={"file": (f"e2e-{RUN}.txt", body, "text/plain")},
    )
    # The real worker extracts and indexes the text.
    deadline = time.monotonic() + 90
    version: dict[str, Any] = {}
    while time.monotonic() < deadline:
        version = employee.ok("GET", f"/documents/{document['id']}")["current_version"]
        if version["processing_status"] == "READY" and version["index_status"] in {
            "READY",
            "FAILED",
        }:
            break
        time.sleep(1)
    assert version["processing_status"] == "READY", version
    hits = employee.ok("GET", "/documents/search", params={"q": marker})["results"]
    assert hits and hits[0]["document_id"] == document["id"]
    assert marker in hits[0]["snippet"]
    # Private: another employee gets 404 and never sees it in search.
    assert it.get(f"/documents/{document['id']}").status_code == 404
    seen_by_it = it.ok("GET", "/documents/search", params={"q": marker})["results"]
    assert document["id"] not in {h["document_id"] for h in seen_by_it}
    download = employee.get(f"/documents/{document['id']}/download")
    assert download.status_code == 200 and download.content == body
    # Owners cannot delete without documents:delete; the administrator cleans up.
    assert employee.send("DELETE", f"/documents/{document['id']}").status_code == 403
    people["admin"].ok("DELETE", f"/documents/{document['id']}", 204)
    assert employee.get(f"/documents/{document['id']}").status_code == 404


def test_helpdesk_workflow_with_internal_notes(people: dict[str, Api]) -> None:
    employee, it = people["employee"], people["it"]
    ticket = employee.ok(
        "POST",
        "/tickets",
        201,
        json={"title": f"E2E {RUN} จอไม่ติด", "description": "ทดสอบ", "category": "COMPUTER"},
    )
    queue = it.ok("GET", "/tickets", params={"scope": "unassigned", "q": RUN})["items"]
    assert [t["id"] for t in queue] == [ticket["id"]]
    it.ok("PUT", f"/tickets/{ticket['id']}/assignee", json={"assignee_id": it.me["user"]["id"]})
    it.ok(
        "POST",
        f"/tickets/{ticket['id']}/comments",
        201,
        json={"body": "บันทึกภายใน E2E", "is_internal": True},
    )
    it.ok("POST", f"/tickets/{ticket['id']}/comments", 201, json={"body": "แก้ไขให้แล้ว"})
    it.ok("POST", f"/tickets/{ticket['id']}/status", json={"status": "RESOLVED"})

    seen = [c["body"] for c in employee.ok("GET", f"/tickets/{ticket['id']}/comments")]
    assert seen == ["แก้ไขให้แล้ว"]  # the internal note never reaches the requester
    notes = employee.ok("GET", "/notifications", params={"page_size": 50})["items"]
    assert any(ticket["ticket_number"] in n["title"] for n in notes)
    closed = employee.ok("POST", f"/tickets/{ticket['id']}/status", json={"status": "CLOSED"})
    assert closed["status"] == "CLOSED"
    # Other employees cannot open it.
    assert people["manager"].get(f"/tickets/{ticket['id']}").status_code == 404


def test_reports_respect_scopes(people: dict[str, Api]) -> None:
    manager, employee = people["manager"], people["employee"]
    overview = manager.ok("GET", "/analytics/overview", params={"scope": "department"})
    assert overview["scope"] == "department" and overview["can_export"] is True
    assert employee.get("/analytics/overview", params={"scope": "all"}).status_code == 403
    assert employee.get("/reports/overview.xlsx").status_code == 403
    export = manager.get("/reports/overview.pdf", params={"scope": "department"})
    assert export.status_code == 200 and export.content.startswith(b"%PDF")


def test_administration_endpoints(people: dict[str, Api]) -> None:
    admin, employee = people["admin"], people["employee"]
    assert admin.ok("GET", "/health/details")["details_hidden"] is False
    assert employee.get("/health/details").status_code == 403
    roles = {r["code"] for r in admin.ok("GET", "/roles")}
    assert {"ADMIN", "EMPLOYEE", "IT_SUPPORT"} <= roles
    assert employee.get("/audit-logs").status_code == 403
