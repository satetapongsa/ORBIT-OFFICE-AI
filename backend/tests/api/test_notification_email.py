"""Notification e-mail: preferences, queueing after commit only, delivery outcomes, SMTP."""

from __future__ import annotations

import smtplib
import uuid
from collections.abc import Callable, Iterator
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core import mail
from app.core.notifications import (
    LogPasswordResetNotifier,
    MailPasswordResetNotifier,
    build_reset_notifier,
)
from app.models.notification import NotificationType
from app.services import notification_email, notifications
from tests.conftest import Factory, make_settings, run

AsUser = Callable[..., TestClient]
PREFS = "/api/v1/notifications/preferences"
MAIL_SETTINGS = {"smtp_host": "mail.example.com", "smtp_from": "ORBIT <no-reply@example.com>"}


@pytest.fixture
def dispatched() -> Iterator[list[list[uuid.UUID]]]:
    calls: list[list[uuid.UUID]] = []
    notifications.set_email_dispatcher(calls.append)
    yield calls
    notifications.set_email_dispatcher(None)


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    sent: list[dict[str, str]] = []

    def fake_send(settings: Any, *, to: str, subject: str, text: str) -> None:
        if to.startswith("broken"):
            raise mail.MailError("mailbox unavailable")
        sent.append({"to": to, "subject": subject, "text": text})

    monkeypatch.setattr(notification_email, "send_mail", fake_send)
    return sent


def _status(db: Factory, notification_id: uuid.UUID) -> str | None:
    return db.scalar("SELECT email_status FROM notifications WHERE id = :i", i=notification_id)


def _add(db: Factory, user_id: uuid.UUID, kind: NotificationType, **extra: Any) -> uuid.UUID:
    with Session(db.engine) as session:
        entry = notifications.notify(session, user_id=user_id, type=kind, title="หัวข้อ", **extra)
        session.commit()
        return entry.id


# --- Preferences API ----------------------------------------------------------------------


def test_preferences_default_and_update(as_user: AsUser) -> None:
    client = as_user(["EMPLOYEE"])
    initial = client.get(PREFS).json()
    assert initial["email_available"] is False  # tests run without SMTP
    defaults = {i["type"]: (i["email_enabled"], i["default"]) for i in initial["items"]}
    assert defaults["TICKET"] == (True, True)
    assert defaults["DOCUMENT"] == (False, False)
    assert set(defaults) == {t.value for t in NotificationType}

    updated = client.put(
        PREFS,
        json={
            "items": [
                {"type": "TICKET", "email_enabled": False},
                {"type": "DOCUMENT", "email_enabled": True},
            ]
        },
    )
    assert updated.status_code == 200
    chosen = {i["type"]: i["email_enabled"] for i in updated.json()["items"]}
    assert chosen["TICKET"] is False and chosen["DOCUMENT"] is True
    # Upsert: setting the same type again updates in place.
    client.put(PREFS, json={"items": [{"type": "TICKET", "email_enabled": True}]})
    again = {i["type"]: i["email_enabled"] for i in client.get(PREFS).json()["items"]}
    assert again["TICKET"] is True and again["DOCUMENT"] is True


def test_preferences_are_per_user_and_validated(
    as_user: AsUser, new_client: Callable[[], TestClient]
) -> None:
    alice = as_user(["EMPLOYEE"])
    bob = as_user(["EMPLOYEE"])
    alice.put(PREFS, json={"items": [{"type": "TASK", "email_enabled": False}]})
    bob_task = {i["type"]: i["email_enabled"] for i in bob.get(PREFS).json()["items"]}["TASK"]
    assert bob_task is True
    assert (
        alice.put(PREFS, json={"items": [{"type": "SPAM", "email_enabled": True}]}).status_code
        == 422
    )
    assert new_client().get(PREFS).status_code == 401


# --- Queueing ----------------------------------------------------------------------------


def test_emails_are_queued_only_after_commit(
    db: Factory, dispatched: list[list[uuid.UUID]]
) -> None:
    user = db.user("alice@example.com")
    with Session(db.engine) as session:
        notifications.notify(session, user_id=user, type=NotificationType.SYSTEM, title="ยกเลิก")
        session.rollback()
        assert dispatched == []
        first = notifications.notify(session, user_id=user, type=NotificationType.SYSTEM, title="ก")
        second = notifications.notify(session, user_id=user, type=NotificationType.TASK, title="ข")
        ids = [first.id, second.id]
        assert dispatched == []  # nothing before the commit
        session.commit()
    assert dispatched == [ids]


def test_api_events_queue_their_notifications(
    as_user: AsUser, dispatched: list[list[uuid.UUID]]
) -> None:
    as_user(["IT_SUPPORT"])
    employee = as_user(["EMPLOYEE"])
    response = employee.post("/api/v1/tickets", json={"title": "จอดับ", "description": "เปิดไม่ติด"})
    assert response.status_code == 201
    assert len(dispatched) == 1 and len(dispatched[0]) == 1


# --- Delivery ----------------------------------------------------------------------------


def test_delivery_respects_preferences_and_records_status(
    db: Factory, outbox: list[dict[str, str]]
) -> None:
    settings = make_settings(**MAIL_SETTINGS, frontend_base_url="https://office.example.com")
    alice = db.user("alice@example.com")
    broken = db.user("broken@example.com")
    inactive = db.user("gone@example.com", active=False)
    with db.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO notification_preferences (user_id, type, email_enabled)"
                " VALUES (:u, 'TASK', false)"
            ),
            {"u": alice},
        )
    wanted = _add(db, alice, NotificationType.TICKET, body="รายละเอียด", link_url="/helpdesk/1")
    muted = _add(db, alice, NotificationType.TASK)
    default_off = _add(db, alice, NotificationType.DOCUMENT)
    failing = _add(db, broken, NotificationType.SECURITY)
    to_inactive = _add(db, inactive, NotificationType.SECURITY)

    with Session(db.engine) as session:
        counts = notification_email.send_notification_emails(
            session, settings, [wanted, muted, default_off, failing, to_inactive, uuid.uuid4()]
        )
    assert counts == {"PENDING": 0, "SENT": 1, "SKIPPED": 3, "FAILED": 1}
    assert _status(db, wanted) == "SENT"
    assert _status(db, muted) == "SKIPPED"
    assert _status(db, default_off) == "SKIPPED"
    assert _status(db, failing) == "FAILED"
    assert _status(db, to_inactive) == "SKIPPED"
    assert db.scalar("SELECT emailed_at IS NOT NULL FROM notifications WHERE id = :i", i=wanted)

    [message] = outbox
    assert message["to"] == "alice@example.com"
    assert message["subject"] == "[ORBIT] หัวข้อ"
    assert "https://office.example.com/helpdesk/1" in message["text"]
    assert "https://office.example.com/account" in message["text"]

    # Redelivery of the task never mails twice; a failure may be retried.
    with Session(db.engine) as session:
        again = notification_email.send_notification_emails(session, settings, [wanted, failing])
    assert again["SENT"] == 0 and again["FAILED"] == 1
    assert len(outbox) == 1


def test_delivery_without_smtp_skips(db: Factory, outbox: list[dict[str, str]]) -> None:
    user = db.user("alice@example.com")
    entry = _add(db, user, NotificationType.SECURITY)
    with Session(db.engine) as session:
        notification_email.send_notification_emails(session, make_settings(smtp_host=""), [entry])
    assert _status(db, entry) == "SKIPPED"
    assert outbox == []


# --- SMTP and password reset ---------------------------------------------------------------


class FakeSMTP:
    instances: ClassVar[list[FakeSMTP]] = []

    def __init__(self, host: str, port: int, timeout: float = 0, **_: Any) -> None:
        self.host, self.port = host, port
        self.calls: list[str] = []
        self.messages: list[Any] = []
        FakeSMTP.instances.append(self)

    def __enter__(self) -> FakeSMTP:
        return self

    def __exit__(self, *_: object) -> None:
        self.calls.append("quit")

    def starttls(self, context: Any = None) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append(f"login:{user}")

    def send_message(self, message: Any) -> None:
        if message["To"] == "refused@example.com":
            raise smtplib.SMTPRecipientsRefused({})
        self.messages.append(message)


def test_send_mail_uses_starttls_and_login(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSMTP.instances = []
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    settings = make_settings(
        **MAIL_SETTINGS,
        smtp_port=587,
        smtp_starttls=True,
        smtp_ssl=False,
        smtp_username="robot",
        smtp_password="pw-from-env",
    )
    mail.send_mail(settings, to="alice@example.com", subject="ทดสอบ", text="สวัสดี")
    [smtp] = FakeSMTP.instances
    assert (smtp.host, smtp.port) == ("mail.example.com", 587)
    assert smtp.calls[:2] == ["starttls", "login:robot"]
    [message] = smtp.messages
    assert message["Subject"] == "ทดสอบ"
    assert "no-reply@example.com" in message["From"]
    assert message.get_content().strip() == "สวัสดี"

    with pytest.raises(mail.MailError):
        mail.send_mail(settings, to="refused@example.com", subject="x", text="x")
    with pytest.raises(mail.MailError):
        mail.send_mail(make_settings(smtp_host=""), to="a@example.com", subject="x", text="x")


def test_reset_notifier_mails_the_link_when_smtp_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert isinstance(build_reset_notifier(make_settings(smtp_host="")), LogPasswordResetNotifier)
    settings = make_settings(**MAIL_SETTINGS)
    notifier = build_reset_notifier(settings)
    assert isinstance(notifier, MailPasswordResetNotifier)
    sent: list[dict[str, str]] = []
    monkeypatch.setattr(mail, "send_mail", lambda _s, **kw: sent.append(kw))
    run(
        notifier.send_password_reset(
            email="alice@example.com",
            display_name="อลิซ",
            reset_url="https://office.example.com/reset-password?token=abc",
        )
    )
    [message] = sent
    assert message["to"] == "alice@example.com"
    assert "https://office.example.com/reset-password?token=abc" in message["text"]
