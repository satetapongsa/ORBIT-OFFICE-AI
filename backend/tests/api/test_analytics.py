"""Analytics and reports: scopes by permission, metric correctness, exports, AI summary."""

from __future__ import annotations

import io
import json
import re
import uuid
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import text

from app.services.analytics import SUMMARY_SYSTEM
from tests.ai_support import ScriptedProvider, say
from tests.conftest import Factory

AsUser = Callable[..., TestClient]
OVERVIEW = "/api/v1/analytics/overview"
SUMMARY = "/api/v1/analytics/summary"
REPORTS = "/api/v1/reports"


@dataclass
class Org:
    db: Factory
    sales: uuid.UUID
    manager: TestClient  # MANAGER in SALES
    alice: TestClient  # EMPLOYEE in SALES
    carol: TestClient  # EMPLOYEE in IT
    admin: TestClient  # ADMIN, no department


def _id(client: TestClient) -> uuid.UUID:
    return uuid.UUID(client.get("/api/v1/auth/me").json()["user"]["id"])


def _task(
    db: Factory,
    title: str,
    *,
    creator: uuid.UUID,
    assignee: uuid.UUID,
    department: uuid.UUID,
    status: str = "TODO",
    created: str = "1 day",
    completed: str | None = None,
    due: str | None = None,
    deleted: bool = False,
) -> None:
    with db.engine.begin() as conn:
        task_id = conn.scalar(
            text(
                "INSERT INTO tasks (title, status, priority, created_by, department_id, created_at,"
                " completed_at, due_at, deleted_at) VALUES (:t, :s, 'MEDIUM', :c, :d,"
                " now() - CAST(:created AS interval),"
                " now() - CAST(:completed AS interval), now() + CAST(:due AS interval),"
                " CASE WHEN CAST(:deleted AS boolean) THEN now() END) RETURNING id"
            ),
            {
                "t": title,
                "s": status,
                "c": creator,
                "d": department,
                "created": created,
                "completed": completed,
                "due": due,
                "deleted": deleted,
            },
        )
        conn.execute(
            text("INSERT INTO task_assignees (task_id, user_id) VALUES (:t, :u)"),
            {"t": task_id, "u": assignee},
        )


@pytest.fixture
def org(db: Factory, as_user: AsUser) -> Org:
    sales = db.department("SALES", "ฝ่ายขาย")
    it = db.department("IT", "ฝ่ายไอที")
    o = Org(
        db=db,
        sales=sales,
        manager=as_user(["MANAGER"], email="manager@example.com", department_id=sales),
        alice=as_user(["EMPLOYEE"], email="alice@example.com", department_id=sales),
        carol=as_user(["EMPLOYEE"], email="carol@example.com", department_id=it),
        admin=as_user(["ADMIN"], email="admin@example.com"),
    )
    manager, alice, carol = _id(o.manager), _id(o.alice), _id(o.carol)
    _task(
        db,
        "งานค้างเลยกำหนด",
        creator=manager,
        assignee=alice,
        department=sales,
        created="2 days",
        due="-1 day",
    )
    _task(
        db,
        "งานที่เสร็จแล้ว",
        creator=manager,
        assignee=alice,
        department=sales,
        status="COMPLETED",
        created="5 days",
        completed="3 days",
    )
    _task(
        db,
        '=HYPERLINK("http://evil.example")',
        creator=manager,
        assignee=alice,
        department=sales,
        status="COMPLETED",
        created="60 days",
        completed="50 days",
    )
    _task(db, "งานที่ลบแล้ว", creator=manager, assignee=alice, department=sales, deleted=True)
    _task(
        db,
        "งานฝ่ายไอที",
        creator=carol,
        assignee=carol,
        department=it,
        status="IN_PROGRESS",
        created="1 day",
    )
    for client, title in ((o.alice, "เมาส์เสีย"), (o.carol, "เน็ตช้า")):
        response = client.post("/api/v1/tickets", json={"title": title, "description": "ช่วยด้วย"})
        assert response.status_code == 201
    with db.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO documents (title, owner_id, department_id, visibility, status, category)"
                " VALUES ('นโยบายลา', :o, :d, 'DEPARTMENT', 'ACTIVE', 'POLICY')"
            ),
            {"o": alice, "d": sales},
        )
    return o


def get(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get(OVERVIEW, params=params)
    assert response.status_code == 200, response.text
    return dict(response.json())


def counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {r["key"]: r["count"] for r in rows}


# --- Overview ------------------------------------------------------------------------------


def test_requires_authentication(new_client: Callable[[], TestClient]) -> None:
    assert new_client().get(OVERVIEW).status_code == 401
    assert new_client().get(f"{REPORTS}/overview.xlsx").status_code == 401


def test_own_scope_metrics(org: Org) -> None:
    data = get(org.alice)
    assert data["scope"] == "own"
    assert data["available_scopes"] == ["own"]
    assert data["can_export"] is False
    tasks = data["tasks"]
    assert (tasks["open"], tasks["overdue"], tasks["created"], tasks["completed"]) == (1, 1, 2, 1)
    assert tasks["completion_rate"] == 0.5
    assert tasks["avg_completion_hours"] == 48.0
    assert counts(tasks["by_status"]) == {"TODO": 1, "COMPLETED": 2}  # deleted never counted
    assert tasks["workload"] == []
    assert len(tasks["daily"]) == 30
    assert sum(d["opened"] for d in tasks["daily"]) == 2
    assert data["tickets"]["open"] == 1 and data["tickets"]["opened"] == 1
    assert data["documents"] == {
        "total": 1,
        "uploaded": 1,
        "by_category": [{"key": "POLICY", "count": 1}],
    }


def test_scopes_are_permission_bound(org: Org, as_user: AsUser) -> None:
    for scope in ("department", "all"):
        response = org.alice.get(OVERVIEW, params={"scope": scope})
        assert response.status_code == 403
    assert org.manager.get(OVERVIEW, params={"scope": "all"}).status_code == 403
    # The department scope needs a department.
    assert get(org.admin)["available_scopes"] == ["own", "all"]
    assert org.admin.get(OVERVIEW, params={"scope": "department"}).status_code == 403
    nobody = as_user([])
    assert nobody.get(OVERVIEW).status_code == 403
    assert nobody.get(OVERVIEW).json()["error"]["code"] == "permission_denied"


def test_department_scope(org: Org) -> None:
    data = get(org.manager, scope="department")
    assert data["available_scopes"] == ["own", "department"]
    assert data["can_export"] is True
    assert data["department"]["name"] == "ฝ่ายขาย"
    tasks = data["tasks"]
    assert (tasks["open"], tasks["overdue"], tasks["created"], tasks["completed"]) == (1, 1, 2, 1)
    [row] = tasks["workload"]
    assert row["user"]["display_name"] == "alice@example.com"
    assert (row["open"], row["overdue"], row["completed"]) == (1, 1, 1)
    # Tickets reported by people in the department (Carol is in IT).
    assert data["tickets"]["opened"] == 1
    assert data["documents"]["total"] == 1


def test_all_scope(org: Org) -> None:
    data = get(org.admin, scope="all")
    assert data["tasks"]["open"] == 2
    assert counts(data["tasks"]["by_status"])["IN_PROGRESS"] == 1
    assert data["tickets"]["open"] == 2
    assert counts(data["tickets"]["by_status"]) == {"OPEN": 2}
    assert {r["user"]["display_name"] for r in data["tasks"]["workload"]} == {
        "alice@example.com",
        "carol@example.com",
    }


def test_period_selection_and_validation(org: Org) -> None:
    today = date.fromisoformat(get(org.alice)["date_to"])
    week = get(
        org.alice, date_from=(today - timedelta(days=6)).isoformat(), date_to=today.isoformat()
    )
    assert len(week["tasks"]["daily"]) == 7
    assert week["tasks"]["completed"] == 1
    old = get(
        org.alice,
        date_from=(today - timedelta(days=55)).isoformat(),
        date_to=(today - timedelta(days=45)).isoformat(),
    )
    assert old["tasks"]["completed"] == 1 and old["tasks"]["created"] == 0

    bad = org.alice.get(
        OVERVIEW,
        params={"date_from": today.isoformat(), "date_to": (today - timedelta(days=1)).isoformat()},
    )
    assert bad.status_code == 422
    too_long = org.alice.get(
        OVERVIEW, params={"date_from": (today - timedelta(days=400)).isoformat()}
    )
    assert too_long.status_code == 422
    assert org.alice.get(OVERVIEW, params={"scope": "everything"}).status_code == 422


# --- Exports -------------------------------------------------------------------------------


def pdf_fonts(pdf: bytes) -> set[bytes]:
    """Embedded font names (object streams are compressed)."""
    chunks = [pdf]
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S):
        try:
            chunks.append(zlib.decompress(match.group(1)))
        except zlib.error:
            continue
    return {n for c in chunks for n in re.findall(rb"/BaseFont\s*/([^\s/<>\[\]]+)", c)}


def test_exports_need_reports_export_and_the_scope(org: Org) -> None:
    assert org.alice.get(f"{REPORTS}/overview.xlsx").status_code == 403
    assert org.alice.get(f"{REPORTS}/overview.pdf").status_code == 403
    assert org.manager.get(f"{REPORTS}/overview.xlsx", params={"scope": "all"}).status_code == 403


def test_xlsx_export_lists_only_visible_rows_and_blocks_formulas(org: Org) -> None:
    response = org.manager.get(
        f"{REPORTS}/overview.xlsx",
        params={
            "scope": "department",
            "date_from": (date.today() - timedelta(days=89)).isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "aura-report-department-" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"

    book = load_workbook(io.BytesIO(response.content))
    assert book.sheetnames == ["สรุป", "งาน", "แจ้งปัญหาไอที", "ภาระงาน"]
    titles = [row[0].value for row in book["งาน"].iter_rows(min_row=2)]
    assert set(titles) == {"งานค้างเลยกำหนด", "งานที่เสร็จแล้ว", '=HYPERLINK("http://evil.example")'}
    formula_cell = next(
        row[0] for row in book["งาน"].iter_rows(min_row=2) if str(row[0].value).startswith("=")
    )
    assert formula_cell.data_type == "s"  # stored as text, never evaluated
    # Department counts include Alice's ticket, but the manager cannot open it: not listed.
    assert book["แจ้งปัญหาไอที"].max_row == 1
    summary = {
        row[0].value: row[1].value for row in book["สรุป"].iter_rows(min_row=2) if row[0].value
    }
    assert summary["งานที่ยังไม่เสร็จ"] == 1
    assert summary["แจ้งปัญหาไอทีที่ยังเปิดอยู่"] == 1
    assert org.db.scalar("SELECT count(*) FROM audit_logs WHERE action = 'report.exported'") == 1


def test_pdf_export_renders_thai(org: Org) -> None:
    response = org.admin.get(f"{REPORTS}/overview.pdf", params={"scope": "all"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert any(b"Loma" in name or b"Garuda" in name for name in pdf_fonts(response.content))
    details = org.db.scalar("SELECT metadata FROM audit_logs WHERE action = 'report.exported'")
    assert details["format"] == "pdf" and details["scope"] == "all"


# --- AI summary ----------------------------------------------------------------------------


def test_summary_requires_a_model(org: Org) -> None:
    response = org.alice.post(SUMMARY, json={})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ai_not_configured"


def test_summary_uses_only_the_permitted_statistics(
    org: Org, api_app: FastAPI, as_user: AsUser
) -> None:
    provider = ScriptedProvider()
    api_app.state.chat_provider = provider
    provider.turns.append(say("• งานค้าง 1 งาน เลยกำหนด 1 งาน"))
    response = org.manager.post(SUMMARY, json={"scope": "department"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"] == "• งานค้าง 1 งาน เลยกำหนด 1 งาน"
    assert body["model"] == "test-model"
    [request] = provider.requests
    assert request["system"] == SUMMARY_SYSTEM
    assert request["tools"] == []
    payload = json.loads(request["messages"][0].content)
    assert payload["scope"] == "department" and payload["scope_label"] == "แผนกของฉัน"
    assert payload["tasks"]["open"] == 1
    assert "daily" not in payload["tasks"]

    assert org.manager.post(SUMMARY, json={"scope": "all"}).status_code == 403
    assert as_user([]).post(SUMMARY, json={}).status_code == 403
    provider.turns.append(say(""))
    assert org.alice.post(SUMMARY, json={}).status_code == 503
