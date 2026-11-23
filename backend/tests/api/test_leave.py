"""Leave requests (ADR-068)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from app.models.leave import HalfDay
from app.services.leave import working_days
from tests.conftest import Factory

AsUser = Callable[..., TestClient]
API = "/api/v1/leave"
MONDAY = date(2030, 3, 4)  # a Monday in a future year
assert MONDAY.weekday() == 0


def d(offset: int) -> str:
    return (MONDAY + timedelta(days=offset)).isoformat()


def type_id(client: TestClient, code: str) -> str:
    return next(t["id"] for t in client.get(f"{API}/types").json() if t["code"] == code)


def ask(client: TestClient, code: str, start: int, end: int, **extra: object) -> TestClient:
    return client.post(  # type: ignore[return-value]
        f"{API}/requests",
        json={
            "leave_type_id": type_id(client, code),
            "start_date": d(start),
            "end_date": d(end),
            **extra,
        },
    )


def notes(client: TestClient) -> list[str]:
    return [n["title"] for n in client.get("/api/v1/notifications").json()["items"]]


def test_working_days() -> None:
    assert working_days(MONDAY, MONDAY + timedelta(days=4)) == 5  # Mon-Fri
    assert working_days(MONDAY, MONDAY + timedelta(days=13)) == 10  # two weeks
    assert working_days(MONDAY + timedelta(days=4), MONDAY + timedelta(days=7)) == 2  # Fri-Mon
    assert working_days(MONDAY + timedelta(days=5), MONDAY + timedelta(days=6)) == 0  # weekend
    assert working_days(MONDAY, MONDAY, HalfDay.MORNING) == Decimal("0.5")


def test_request_is_routed_to_the_department_manager_and_approved(
    as_user: AsUser, db: Factory
) -> None:
    sales, it = db.department("SALES", "ฝ่ายขาย"), db.department("IT", "ฝ่ายไอที")
    staff = as_user(["EMPLOYEE"], department_id=sales)
    boss = as_user(["MANAGER"], department_id=sales)
    other_boss = as_user(["MANAGER"], department_id=it)
    hr = as_user(["HR"])

    created = ask(staff, "ANNUAL", 0, 1, reason="ไปเที่ยวกับครอบครัว")
    assert created.status_code == 201, created.text
    item = created.json()
    assert item["days"] == "2.0" and item["status"] == "PENDING" and item["can_cancel"] is True
    assert any("ขอลาพักร้อน 2 วัน" in t for t in notes(boss))
    assert not any("ขอลาพักร้อน" in t for t in notes(other_boss))  # other department
    assert not any("ขอลาพักร้อน" in t for t in notes(hr))  # the manager is there

    mine = staff.get(f"{API}/me", params={"year": 2030}).json()
    annual = next(b for b in mine["balances"] if b["leave_type"]["code"] == "ANNUAL")
    assert (annual["quota"], annual["used"], annual["pending"], annual["remaining"]) == (
        "6.0",
        "0",
        "2.0",
        "4.0",
    )

    queue = boss.get(f"{API}/requests", params={"scope": "approvals"}).json()
    assert [(q["id"], q["reason"], q["can_decide"]) for q in queue] == [
        (item["id"], "ไปเที่ยวกับครอบครัว", True)
    ]
    assert other_boss.get(f"{API}/requests", params={"scope": "approvals"}).json() == []
    url = f"{API}/requests/{item['id']}/decision"
    assert other_boss.post(url, json={"approve": True}).status_code == 404
    assert boss.post(url, json={"approve": False}).status_code == 422  # reason required
    approved = boss.post(url, json={"approve": True, "note": "ขอให้สนุก"})
    assert approved.status_code == 200 and approved.json()["status"] == "APPROVED"
    assert approved.json()["decided_by_name"]
    assert any("ได้รับอนุมัติแล้ว" in t for t in notes(staff))
    assert boss.post(url, json={"approve": True}).status_code == 409  # already decided

    annual = next(
        b
        for b in staff.get(f"{API}/me", params={"year": 2030}).json()["balances"]
        if b["leave_type"]["code"] == "ANNUAL"
    )
    assert (annual["used"], annual["pending"], annual["remaining"]) == ("2.0", "0", "4.0")


def test_validation_quota_overlap_and_half_days(as_user: AsUser) -> None:
    staff = as_user(["EMPLOYEE"])
    assert ask(staff, "PERSONAL", 5, 6).status_code == 422  # weekend only
    assert ask(staff, "PERSONAL", 1, 0).status_code == 422  # end before start
    assert ask(staff, "PERSONAL", 0, 1, half_day="MORNING").status_code == 422  # half on 2 days
    cross = staff.post(
        f"{API}/requests",
        json={
            "leave_type_id": type_id(staff, "SICK"),
            "start_date": "2030-12-31",
            "end_date": "2031-01-02",
        },
    )
    assert cross.status_code == 422
    too_many = ask(staff, "PERSONAL", 0, 3)  # 4 days, quota 3
    assert too_many.status_code == 422 and "คงเหลือ 3 วัน" in str(too_many.json())

    assert ask(staff, "PERSONAL", 0, 0, half_day="MORNING").status_code == 201
    assert ask(staff, "PERSONAL", 0, 0, half_day="AFTERNOON").status_code == 201
    clash = ask(staff, "SICK", 0, 2)
    assert clash.status_code == 409
    assert ask(staff, "PERSONAL", 2, 3).status_code == 201  # 1 + 2 = 3 days: exactly the quota
    assert ask(staff, "PERSONAL", 7, 7).status_code == 422  # nothing left
    assert ask(staff, "UNPAID", 7, 11).status_code == 201  # no limit


def test_cancel_rules_and_self_approval(as_user: AsUser, db: Factory) -> None:
    sales = db.department("SALES")
    boss = as_user(["MANAGER"], department_id=sales)
    hr = as_user(["HR"])

    own = ask(boss, "ANNUAL", 0, 0).json()
    assert any("ขอลาพักร้อน" in t for t in notes(hr))  # nobody else in the department decides
    assert (
        boss.post(f"{API}/requests/{own['id']}/decision", json={"approve": True}).status_code == 403
    )
    assert (
        hr.post(f"{API}/requests/{own['id']}/decision", json={"approve": True}).status_code == 200
    )
    cancelled = boss.post(f"{API}/requests/{own['id']}/cancel")  # approved, not started yet
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    assert boss.post(f"{API}/requests/{own['id']}/cancel").status_code == 409

    # An approved leave that has started can only be cancelled by HR.
    start = date.today()
    while start.weekday() > 4:
        start -= timedelta(days=1)
    started = boss.post(
        f"{API}/requests",
        json={
            "leave_type_id": type_id(boss, "SICK"),
            "start_date": start.isoformat(),
            "end_date": start.isoformat(),
        },
    ).json()
    hr.post(f"{API}/requests/{started['id']}/decision", json={"approve": True})
    assert boss.post(f"{API}/requests/{started['id']}/cancel").status_code == 409
    assert hr.post(f"{API}/requests/{started['id']}/cancel").status_code == 200
    assert any("ใบลาของคุณถูกยกเลิก" in t for t in notes(boss))


def test_team_calendar_shows_who_is_away_without_reasons(as_user: AsUser, db: Factory) -> None:
    sales, it = db.department("SALES"), db.department("IT")
    staff = as_user(["EMPLOYEE"], department_id=sales)
    colleague = as_user(["EMPLOYEE"], department_id=sales)
    outsider = as_user(["EMPLOYEE"], department_id=it)
    hr = as_user(["HR"])
    item = ask(staff, "SICK", 2, 2, reason="ไปหาหมอฟัน").json()
    hr.post(f"{API}/requests/{item['id']}/decision", json={"approve": True})

    period = {"start": d(0), "end": d(6)}
    seen = colleague.get(f"{API}/calendar", params=period).json()
    assert [(e["id"], e["reason"], e["can_cancel"]) for e in seen] == [(item["id"], "", False)]
    assert outsider.get(f"{API}/calendar", params=period).json() == []
    assert hr.get(f"{API}/calendar", params=period).json()[0]["reason"] == "ไปหาหมอฟัน"
    assert colleague.get(f"{API}/requests", params={"scope": "department"}).status_code == 403


def test_hr_changes_types_and_personal_quotas(as_user: AsUser) -> None:
    hr, staff = as_user(["HR"]), as_user(["EMPLOYEE"])
    annual = type_id(hr, "ANNUAL")
    assert staff.patch(f"{API}/types/{annual}", json={"days_per_year": 10}).status_code == 403
    assert (
        hr.patch(f"{API}/types/{annual}", json={"days_per_year": 10}).json()["days_per_year"]
        == "10.0"
    )
    me = staff.get("/api/v1/auth/me").json()["user"]["id"]
    assert (
        hr.put(
            f"{API}/quotas", json={"user_id": me, "leave_type_id": annual, "year": 2030, "days": 15}
        ).status_code
        == 204
    )
    balance = lambda: next(  # noqa: E731
        b
        for b in staff.get(f"{API}/me", params={"year": 2030}).json()["balances"]
        if b["leave_type"]["code"] == "ANNUAL"
    )
    assert balance()["quota"] == "15.0"
    hr.put(
        f"{API}/quotas", json={"user_id": me, "leave_type_id": annual, "year": 2030, "days": None}
    )
    assert balance()["quota"] == "10.0"
    personal = type_id(hr, "PERSONAL")
    hr.patch(f"{API}/types/{personal}", json={"is_active": False})
    assert "PERSONAL" not in [t["code"] for t in staff.get(f"{API}/types").json()]
    assert staff.get(f"{API}/preview", params={"start_date": d(0), "end_date": d(9)}).json() == {
        "days": "8"
    }
