"""Company announcements (ADR-067)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.conftest import Factory

AsUser = Callable[..., TestClient]
API = "/api/v1/announcements"


def test_hr_publishes_and_the_right_people_read_it(as_user: AsUser, db: Factory) -> None:
    sales, it = db.department("SALES", "ฝ่ายขาย"), db.department("IT", "ฝ่ายไอที")
    hr = as_user(["HR"])
    seller = as_user(["EMPLOYEE"], department_id=sales)
    techie = as_user(["EMPLOYEE"], department_id=it)

    everyone = hr.post(
        API, json={"title": "วันหยุดปีใหม่", "body": "หยุด 31 ธ.ค. - 2 ม.ค.", "important": True}
    )
    assert everyone.status_code == 201, everyone.text
    for_sales = hr.post(
        API, json={"title": "ประชุมทีมขาย", "body": "วันศุกร์ 10 โมง", "department_id": str(sales)}
    ).json()
    assert for_sales["department_name"] == "ฝ่ายขาย"

    assert {a["title"] for a in seller.get(API).json()["items"]} == {"วันหยุดปีใหม่", "ประชุมทีมขาย"}
    assert [a["title"] for a in techie.get(API).json()["items"]] == ["วันหยุดปีใหม่"]
    assert techie.get(f"{API}/{for_sales['id']}").status_code == 404

    # Everyone who can see it is notified, the author is not.
    titles = lambda c: [n["title"] for n in c.get("/api/v1/notifications").json()["items"]]  # noqa: E731
    assert "ประกาศสำคัญ: วันหยุดปีใหม่" in titles(seller)
    assert "ประกาศใหม่: ประชุมทีมขาย" in titles(seller)
    assert "ประกาศใหม่: ประชุมทีมขาย" not in titles(techie)
    assert not any("วันหยุดปีใหม่" in t for t in titles(hr))

    # Unread markers and read statistics.
    assert seller.get(f"{API}/unread-count").json() == {"unread_count": 2}
    assert seller.post(f"{API}/{for_sales['id']}/read").json() == {"unread_count": 1}
    seller.post(f"{API}/{for_sales['id']}/read")  # idempotent
    item = next(a for a in seller.get(API).json()["items"] if a["id"] == for_sales["id"])
    assert item["is_read"] is True and item["read_count"] is None  # statistics are for HR only
    stats = hr.get(f"{API}/{for_sales['id']}").json()
    assert (stats["read_count"], stats["audience_count"]) == (1, 1)
    seller.post(f"{API}/read-all")
    assert seller.get(f"{API}/unread-count").json() == {"unread_count": 0}


def test_only_managers_write_and_pinned_comes_first(as_user: AsUser) -> None:
    hr, staff = as_user(["HR"]), as_user(["EMPLOYEE"])
    assert staff.post(API, json={"title": "x", "body": "y"}).status_code == 403
    first = hr.post(API, json={"title": "เก่า", "body": "a", "notify": False}).json()
    hr.post(API, json={"title": "ใหม่", "body": "b", "notify": False})
    assert staff.patch(f"{API}/{first['id']}", json={"pinned": True}).status_code == 403
    pinned = hr.patch(f"{API}/{first['id']}", json={"pinned": True, "title": "ปักหมุดแล้ว"})
    assert pinned.status_code == 200 and pinned.json()["edited"] in (True, False)
    assert [a["title"] for a in staff.get(API).json()["items"]] == ["ปักหมุดแล้ว", "ใหม่"]
    assert staff.delete(f"{API}/{first['id']}").status_code == 403
    assert hr.delete(f"{API}/{first['id']}").status_code == 204
    assert [a["title"] for a in staff.get(API).json()["items"]] == ["ใหม่"]
    assert hr.post(API, json={"title": "", "body": "x"}).status_code == 422
    assert hr.post(API, json={"title": "x", "body": "ก" * 10001}).status_code == 422


def test_expired_announcements_disappear_for_readers(as_user: AsUser, db: Factory) -> None:
    hr, staff = as_user(["HR"]), as_user(["EMPLOYEE"])
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    soon = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    assert hr.post(API, json={"title": "x", "body": "y", "expires_at": past}).status_code == 422
    item = hr.post(API, json={"title": "โปรโมชันวันนี้", "body": "y", "expires_at": soon}).json()
    assert [a["title"] for a in staff.get(API).json()["items"]] == ["โปรโมชันวันนี้"]

    with db.engine.begin() as conn:
        from sqlalchemy import text

        conn.execute(
            text(
                "UPDATE announcements SET published_at = now() - interval '2 days',"
                " expires_at = now() - interval '1 hour'"
            )
        )
    assert staff.get(API).json()["items"] == []
    assert staff.get(f"{API}/unread-count").json() == {"unread_count": 0}
    everything = hr.get(API, params={"include_expired": True}).json()["items"]
    assert [(a["id"], a["expired"]) for a in everything] == [(item["id"], True)]
    cleared = hr.patch(f"{API}/{item['id']}", json={"clear_expiry": True}).json()
    assert cleared["expires_at"] is None and cleared["expired"] is False


def test_unknown_department_is_rejected(as_user: AsUser) -> None:
    hr = as_user(["HR"])
    bad = hr.post(
        API,
        json={"title": "x", "body": "y", "department_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert bad.status_code == 422
