"""Attendance check-in / check-out (ADR-069)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.services.attendance import is_late
from tests.conftest import Factory, make_settings

AsUser = Callable[..., TestClient]
API = "/api/v1/attendance"
BKK = ZoneInfo("Asia/Bangkok")


def test_is_late_uses_start_time_and_grace() -> None:
    settings = make_settings(work_start_time="09:00", late_grace_minutes=15)
    assert not is_late(datetime(2026, 11, 23, 9, 15, tzinfo=BKK), settings)
    assert is_late(datetime(2026, 11, 23, 9, 15, 1, tzinfo=BKK), settings)
    assert not is_late(datetime(2026, 11, 23, 7, 30, tzinfo=BKK), settings)


def test_check_in_and_out_once_a_day(as_user: AsUser, api_app: FastAPI) -> None:
    api_app.state.settings.work_start_time = "00:00"  # any time today counts as late
    api_app.state.settings.late_grace_minutes = 0
    me = as_user(["EMPLOYEE"])
    first = me.get(f"{API}/today").json()
    assert first["record"] is None and first["hours"]["start"] == "00:00"

    assert me.post(f"{API}/check-out", json={}).status_code == 409  # not checked in yet
    done = me.post(f"{API}/check-in", json={"work_mode": "WFH", "note": "ทำงานที่บ้าน"})
    assert done.status_code == 200, done.text
    record = done.json()["record"]
    assert record["work_mode"] == "WFH" and record["late"] is True
    assert record["check_in_note"] == "ทำงานที่บ้าน" and record["worked_minutes"] is None
    assert me.post(f"{API}/check-in", json={}).status_code == 409

    out = me.post(f"{API}/check-out", json={"note": "เสร็จงาน"}).json()["record"]
    assert out["check_out_at"] is not None and out["worked_minutes"] == 0
    assert me.post(f"{API}/check-out", json={}).status_code == 409

    month = me.get(f"{API}/me").json()
    assert month["summary"]["days_present"] == 1
    assert month["summary"]["late_days"] == 1 and month["summary"]["wfh_days"] == 1
    assert month["summary"]["average_check_in"] is not None
    assert me.get(f"{API}/me", params={"month": "2026-13"}).status_code == 422
    assert me.post(f"{API}/check-in", json={"work_mode": "BEACH"}).status_code == 422


def test_on_time_when_before_the_start(as_user: AsUser, api_app: FastAPI) -> None:
    api_app.state.settings.work_start_time = "23:59"
    api_app.state.settings.late_grace_minutes = 0
    me = as_user(["EMPLOYEE"])
    if datetime.now(BKK).strftime("%H:%M") == "23:59":  # pragma: no cover - one-minute window
        return
    assert me.post(f"{API}/check-in", json={}).json()["record"]["late"] is False


def test_team_board_shows_leave_and_respects_scope(
    as_user: AsUser, db: Factory, api_app: FastAPI
) -> None:
    sales, it = db.department("SALES", "ฝ่ายขาย"), db.department("IT", "ฝ่ายไอที")
    boss = as_user(["MANAGER"], department_id=sales)
    present = as_user(["EMPLOYEE"], department_id=sales)
    away = as_user(["EMPLOYEE"], department_id=sales)
    as_user(["EMPLOYEE"], department_id=sales)  # not checked in
    as_user(["EMPLOYEE"], department_id=it)
    hr = as_user(["HR"])
    staff = as_user(["EMPLOYEE"], department_id=sales)

    present.post(f"{API}/check-in", json={})
    away_id = away.get("/api/v1/auth/me").json()["user"]["id"]
    today = datetime.now(BKK).date()
    with db.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO leave_types (code, name, days_per_year, color, is_active, sort_order)"
                " VALUES ('SICK', 'ลาป่วย', 30, 'rose', true, 1) ON CONFLICT DO NOTHING"
            )
        )
        conn.execute(
            text(
                "INSERT INTO leave_requests (user_id, leave_type_id, start_date, end_date,"
                " half_day, days, reason, status) SELECT :u, id, :d, :d, 'NONE', 1, '', 'APPROVED'"
                " FROM leave_types WHERE code = 'SICK'"
            ),
            {"u": away_id, "d": today},
        )

    board = boss.get(f"{API}/team").json()
    assert len(board["rows"]) == 5  # the sales department only (boss, staff and three others)
    assert (board["present"], board["on_leave"], board["missing"]) == (1, 1, 3)
    assert any(r["on_leave"] == "ลาป่วย" for r in board["rows"])
    assert staff.get(f"{API}/team").status_code == 403
    assert boss.get(f"{API}/team", params={"department_id": str(it)}).status_code == 403
    assert len(hr.get(f"{API}/team", params={"department_id": str(it)}).json()["rows"]) == 1

    report = boss.get(f"{API}/report").json()
    row = next(r for r in report["rows"] if r["person"]["id"] == away_id)
    assert row["leave_days"] == 1.0 and report["working_days"] >= 20
    csv = boss.get(f"{API}/report.csv")
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    assert csv.content.startswith("﻿".encode()) and "วันที่มาทำงาน" in csv.text
