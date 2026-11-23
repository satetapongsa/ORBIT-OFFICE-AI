"""Calendar and meetings (ADR-070)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.meetings import send_due_reminders
from tests.conftest import Factory

AsUser = Callable[..., TestClient]
API = "/api/v1/calendar"
SOON = (datetime.now(UTC) + timedelta(days=3)).replace(minute=0, second=0, microsecond=0)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def uid(client: TestClient) -> str:
    return str(client.get("/api/v1/auth/me").json()["user"]["id"])


def titles(client: TestClient) -> list[str]:
    return [n["title"] for n in client.get("/api/v1/notifications").json()["items"]]


def plan(
    client: TestClient, *people: TestClient, start: datetime = SOON, hours: int = 1, **extra: object
):
    return client.post(
        f"{API}/meetings",
        json={
            "title": "ประชุมทีม",
            "location": "ห้อง 3",
            "start_at": iso(start),
            "end_at": iso(start + timedelta(hours=hours)),
            "attendee_ids": [uid(p) for p in people],
            **extra,
        },
    )


def test_invite_respond_and_privacy(as_user: AsUser) -> None:
    boss, alice, bob, outsider = (as_user(["EMPLOYEE"]) for _ in range(4))
    created = plan(boss, alice, bob, online_url="https://meet.example.com/abc")
    assert created.status_code == 201, created.text
    meeting = created.json()
    assert meeting["is_organizer"] is True and meeting["my_response"] == "ACCEPTED"
    assert [a["is_organizer"] for a in meeting["attendees"]] == [True, False, False]
    assert any("เชิญคุณประชุม: ประชุมทีม" in t for t in titles(alice))
    assert not any("ประชุมทีม" in t for t in titles(boss))

    url = f"{API}/meetings/{meeting['id']}"
    assert outsider.get(url).status_code == 404
    seen = alice.get(url).json()
    assert seen["my_response"] == "PENDING" and seen["is_organizer"] is False
    period = {
        "start": SOON.date().isoformat(),
        "end": (SOON + timedelta(days=1)).date().isoformat(),
    }
    assert [m["id"] for m in alice.get(f"{API}/events", params=period).json()["meetings"]] == [
        meeting["id"]
    ]
    assert outsider.get(f"{API}/events", params=period).json()["meetings"] == []

    assert (
        alice.post(f"{url}/respond", json={"response": "ACCEPTED"}).json()["my_response"]
        == "ACCEPTED"
    )
    bob.post(f"{url}/respond", json={"response": "DECLINED"})
    assert any("ปฏิเสธการประชุม" in t for t in titles(boss))
    assert boss.post(f"{url}/respond", json={"response": "DECLINED"}).status_code == 409
    assert outsider.post(f"{url}/respond", json={"response": "ACCEPTED"}).status_code == 404


def test_organizer_changes_time_attendees_and_cancels(as_user: AsUser) -> None:
    boss, alice, bob, carol = (as_user(["EMPLOYEE"]) for _ in range(4))
    meeting = plan(boss, alice, bob).json()
    url = f"{API}/meetings/{meeting['id']}"
    alice.post(f"{url}/respond", json={"response": "ACCEPTED"})
    assert alice.patch(url, json={"title": "x"}).status_code == 403

    later = SOON + timedelta(hours=2)
    moved = boss.patch(
        url,
        json={
            "start_at": iso(later),
            "end_at": iso(later + timedelta(hours=1)),
            "attendee_ids": [uid(alice), uid(carol)],
        },
    )
    assert moved.status_code == 200, moved.text
    responses = {a["display_name"]: a["response"] for a in moved.json()["attendees"]}
    assert sorted(responses.values()) == ["ACCEPTED", "PENDING", "PENDING"]  # reset for new time
    assert any("อัปเดตการประชุม" in t for t in titles(alice))
    assert any("เชิญคุณประชุม" in t for t in titles(carol))
    assert any("ถูกนำออกจากการประชุม" in t for t in titles(bob))
    assert bob.get(url).status_code == 404

    cancelled = boss.post(f"{url}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["cancelled"] is True
    assert any("ยกเลิกการประชุม" in t for t in titles(carol))
    assert carol.post(f"{url}/respond", json={"response": "ACCEPTED"}).status_code == 409
    assert boss.post(f"{url}/cancel").status_code == 409


def test_validation(as_user: AsUser, db: Factory) -> None:
    boss, alice = as_user(["EMPLOYEE"]), as_user(["EMPLOYEE"])
    assert plan(boss, start=SOON, hours=25).status_code == 422
    assert plan(boss, start=datetime.now(UTC) - timedelta(days=2)).status_code == 422
    assert plan(boss, online_url="http://insecure.example.com").status_code == 422
    bad = boss.post(
        f"{API}/meetings",
        json={"title": "x", "start_at": iso(SOON), "end_at": iso(SOON - timedelta(hours=1))},
    )
    assert bad.status_code == 422
    alice_id = uid(alice)
    with db.engine.begin() as conn:
        conn.execute(text("UPDATE users SET is_active = false WHERE id = :u"), {"u": alice_id})
    inactive = boss.post(
        f"{API}/meetings",
        json={
            "title": "x",
            "start_at": iso(SOON),
            "end_at": iso(SOON + timedelta(hours=1)),
            "attendee_ids": [alice_id],
        },
    )
    assert inactive.status_code == 422
    assert (
        as_user([])
        .get(f"{API}/events", params={"start": "2030-01-01", "end": "2030-01-31"})
        .status_code
        == 403
    )


def test_availability_hides_titles_of_other_meetings(as_user: AsUser, db: Factory) -> None:
    boss, alice, planner = (as_user(["EMPLOYEE"]) for _ in range(3))
    plan(boss, alice)  # alice is busy at SOON (planner is not part of it)
    with db.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO leave_types (code, name, days_per_year, color, is_active, sort_order)"
                " VALUES ('SICK', 'ลาป่วย', 30, 'rose', true, 1) ON CONFLICT DO NOTHING"
            )
        )
    hr = as_user(["HR"])
    carol = as_user(["EMPLOYEE"])
    with db.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO leave_requests (user_id, leave_type_id, start_date, end_date, half_day,"
                " days, reason, status) SELECT :u, id, :d, :d, 'NONE', 1, '', 'APPROVED'"
                " FROM leave_types WHERE code = 'SICK'"
            ),
            {"u": uid(carol), "d": SOON.date()},
        )
    found = planner.post(
        f"{API}/availability",
        json={
            "user_ids": [uid(alice), uid(carol), uid(hr)],
            "start_at": iso(SOON + timedelta(minutes=30)),
            "end_at": iso(SOON + timedelta(hours=2)),
        },
    ).json()["conflicts"]
    kinds = sorted((c["kind"], c["detail"].split(" ")[0]) for c in found)
    assert kinds == [("leave", "ลาป่วยในวันนั้น"), ("meeting", "ติดประชุมอื่น")]
    own_view = boss.post(
        f"{API}/availability",
        json={
            "user_ids": [uid(alice)],
            "start_at": iso(SOON),
            "end_at": iso(SOON + timedelta(hours=1)),
        },
    ).json()["conflicts"]
    assert own_view[0]["detail"].startswith("ติด“ประชุมทีม”")


def test_reminders_go_out_once(as_user: AsUser, db: Factory) -> None:
    boss, alice, bob = (as_user(["EMPLOYEE"]) for _ in range(3))
    soon = datetime.now(UTC) + timedelta(minutes=10)
    meeting = plan(boss, alice, bob, start=soon, reminder_minutes=15).json()
    bob.post(f"{API}/meetings/{meeting['id']}/respond", json={"response": "DECLINED"})
    plan(boss, alice, start=datetime.now(UTC) + timedelta(hours=3), reminder_minutes=15)  # not due

    with Session(db.engine) as session:
        assert send_due_reminders(session, "Asia/Bangkok") == 1
        session.commit()
    with Session(db.engine) as session:
        assert send_due_reminders(session, "Asia/Bangkok") == 0
        session.commit()
    assert any(t.startswith("อีก 15 นาที: ประชุมทีม") for t in titles(alice))
    assert any(t.startswith("อีก 15 นาที") for t in titles(boss))
    assert not any(t.startswith("อีก 15 นาที") for t in titles(bob))  # declined
