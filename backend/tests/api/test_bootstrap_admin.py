"""`python -m app.cli bootstrap-admin`: first administrator from environment variables."""

from __future__ import annotations

import pytest

from app import cli
from tests.conftest import Factory

PASSWORD = "Bootstrap-Admin-Pass-2026"


def _admins(db: Factory) -> int:
    return int(
        db.scalar(
            "SELECT count(*) FROM users u JOIN user_roles ur ON ur.user_id = u.id"
            " JOIN roles r ON r.id = ur.role_id WHERE r.code = 'ADMIN'"
        )
    )


def test_skipped_without_variables(db: Factory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ADMIN_BOOTSTRAP_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_BOOTSTRAP_PASSWORD", raising=False)
    assert cli.main(["bootstrap-admin"]) == 0
    assert _admins(db) == 0


def test_creates_once_and_never_overwrites(db: Factory, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_BOOTSTRAP_EMAIL", "Boss@Example.com")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_PASSWORD", PASSWORD)
    monkeypatch.setenv("ADMIN_BOOTSTRAP_FIRST_NAME", "เจ้าของ")
    assert cli.main(["bootstrap-admin"]) == 0
    assert _admins(db) == 1
    first_hash = db.scalar("SELECT password_hash FROM users WHERE email = 'boss@example.com'")
    assert db.scalar("SELECT display_name FROM users") == "เจ้าของ ORBIT"

    monkeypatch.setenv("ADMIN_BOOTSTRAP_PASSWORD", "Another-Pass-Entirely-99")
    assert cli.main(["bootstrap-admin"]) == 0  # next restart: nothing changes
    assert _admins(db) == 1
    assert db.scalar("SELECT password_hash FROM users") == first_hash


def test_weak_password_is_refused_without_stopping_start_up(
    db: Factory, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ADMIN_BOOTSTRAP_EMAIL", "boss@example.com")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_PASSWORD", "short")
    assert cli.main(["bootstrap-admin"]) == 0
    assert _admins(db) == 0
    assert "refused" in capsys.readouterr().err
