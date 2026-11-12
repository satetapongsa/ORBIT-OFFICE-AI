"""First administrator of a new installation (`python -m app.cli create-admin`)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.errors import ValidationFailedError
from app.services.bootstrap import BootstrapError, create_admin
from tests.conftest import Factory, login, make_settings

STRONG = "Orbit-First-Admin-2026!"


def _create(db: Factory, **overrides: str) -> None:
    values = {
        "email": "Owner@Example.com",
        "first_name": "สมศักดิ์",
        "last_name": "ผู้ดูแล",
        "employee_code": "ADM-0001",
        "password": STRONG,
        **overrides,
    }
    with Session(db.engine) as session:
        create_admin(session, make_settings(), **values)


def test_creates_an_administrator_who_can_sign_in(
    db: Factory, new_client: Callable[[], TestClient]
) -> None:
    _create(db)
    me = login(new_client(), "owner@example.com", STRONG).get("/api/v1/auth/me").json()
    assert {r["code"] for r in me["user"]["roles"]} == {"ADMIN", "EMPLOYEE"}
    assert "roles:manage" in me["permissions"]
    assert (
        db.scalar(
            "SELECT count(*) FROM audit_logs WHERE action = 'user.created' AND actor_id IS NULL"
        )
        == 1
    )


@pytest.mark.parametrize(
    ("override", "error"),
    [
        ({"email": "not-an-email"}, BootstrapError),
        ({"password": "short"}, ValidationFailedError),
        ({"password": "password1234"}, ValidationFailedError),
    ],
)
def test_rejects_bad_input(db: Factory, override: dict[str, str], error: type[Exception]) -> None:
    with pytest.raises(error):
        _create(db, **override)
    assert db.scalar("SELECT count(*) FROM users") == 0


def test_refuses_duplicates(db: Factory) -> None:
    _create(db)
    with pytest.raises(BootstrapError, match="already exists"):
        _create(db, email="OWNER@example.com", employee_code="ADM-0002")
    with pytest.raises(BootstrapError, match="employee code"):
        _create(db, email="second@example.com")
