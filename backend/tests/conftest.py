"""Shared pytest fixtures.

Tests run against a dedicated database (``orbit_office_test`` by default, or
``ORBIT_TEST_DATABASE_URL``) that is created and migrated automatically, so the development
database is never touched. Tests that need PostgreSQL use the ``db`` fixture and are skipped
with a clear reason when the server is unreachable.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.engine import Engine

# --- Environment (must run before the app reads settings) ------------------------------
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("STORAGE_AUTO_CREATE_BUCKET", "false")
os.environ["DATABASE_USE_NULL_POOL"] = "true"  # every TestClient runs its own event loop
# Tests never send real e-mail (Compose points containers at Mailpit); mail tests opt in.
os.environ["SMTP_HOST"] = ""

_BASE_DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://orbit:orbit_dev_password@127.0.0.1:5432/orbit_office"
)
TEST_DATABASE_URL = os.environ.get("ORBIT_TEST_DATABASE_URL") or make_url(_BASE_DB_URL).set(
    database="orbit_office_test"
).render_as_string(hide_password=False)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from app.core.config import Settings  # noqa: E402
from app.core.event_loop import selector_event_loop  # noqa: E402
from app.core.rate_limit import InMemoryRateLimiter  # noqa: E402
from app.core.security import CSRF_COOKIE, CSRF_HEADER, hash_password, utcnow  # noqa: E402
from app.main import create_app  # noqa: E402

TEST_PASSWORD = "Test-Passw0rd-ORBIT!"  # used only for accounts created inside the test DB
_TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD)

BACKEND_OPTIONS = {"loop_factory": selector_event_loop} if sys.platform == "win32" else {}


def make_settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "environment": "test",
        "storage_auto_create_bucket": False,
        "log_json": False,
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


@pytest.fixture
def settings_factory() -> Callable[..., Settings]:
    return make_settings


@pytest.fixture
def app_factory() -> Callable[..., FastAPI]:
    def _factory(**overrides: Any) -> FastAPI:
        return create_app(make_settings(**overrides))

    return _factory


@pytest.fixture
def client(app_factory: Callable[..., FastAPI]) -> Iterator[TestClient]:
    # Not used as a context manager: lifespan (bucket creation) is not needed for unit tests.
    yield TestClient(app_factory(), raise_server_exceptions=False, backend_options=BACKEND_OPTIONS)


# --- Database fixtures ------------------------------------------------------------------


def _ensure_test_database() -> Engine:
    url = make_url(TEST_DATABASE_URL)
    if not url.database or "test" not in url.database:
        raise RuntimeError(f"refusing to use non-test database {url.database!r} for tests")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": url.database}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()

    from alembic import command
    from alembic.config import Config

    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option(
        "script_location", os.path.join(os.path.dirname(__file__), "..", "migrations")
    )
    command.upgrade(cfg, "head")
    return create_engine(TEST_DATABASE_URL)


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    try:
        engine = _ensure_test_database()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL test database unavailable ({type(exc).__name__}); start the stack")
    yield engine
    engine.dispose()


def _reset(engine: Engine) -> None:
    from app.models import Base
    from app.services.rbac_sync import sync_rbac

    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        sync_rbac(session)
        session.commit()


@dataclass
class Factory:
    """Creates rows directly in the test database (bypassing the API under test)."""

    engine: Engine
    created_users: list[uuid.UUID] = field(default_factory=list)

    def department(self, code: str, name: str | None = None) -> uuid.UUID:
        with self.engine.begin() as conn:
            return uuid.UUID(
                str(
                    conn.scalar(
                        text("INSERT INTO departments (code, name) VALUES (:c, :n) RETURNING id"),
                        {"c": code, "n": name or code},
                    )
                )
            )

    def user(
        self,
        email: str,
        roles: list[str] | None = None,
        *,
        department_id: uuid.UUID | None = None,
        active: bool = True,
        password_hash: str | None = _TEST_PASSWORD_HASH,
    ) -> uuid.UUID:
        roles = ["EMPLOYEE"] if roles is None else roles
        with self.engine.begin() as conn:
            user_id = conn.scalar(
                text(
                    "INSERT INTO users (employee_code, email, password_hash, first_name, last_name,"
                    " display_name, department_id, employment_status, is_active, password_changed_at)"
                    " VALUES (:code, :email, :ph, 'Test', 'User', :email, :dept, 'ACTIVE', :active,"
                    " :changed) RETURNING id"
                ),
                {
                    "code": f"T-{uuid.uuid4().hex[:8]}",
                    "email": email,
                    "ph": password_hash,
                    "dept": department_id,
                    "active": active,
                    "changed": utcnow().replace(microsecond=0),
                },
            )
            for role in roles:
                conn.execute(
                    text(
                        "INSERT INTO user_roles (user_id, role_id)"
                        " SELECT :uid, id FROM roles WHERE code = :code"
                    ),
                    {"uid": user_id, "code": role},
                )
        uid = uuid.UUID(str(user_id))
        self.created_users.append(uid)
        return uid

    def role_id(self, code: str) -> uuid.UUID:
        with self.engine.connect() as conn:
            return uuid.UUID(
                str(conn.scalar(text("SELECT id FROM roles WHERE code = :c"), {"c": code}))
            )

    def scalar(self, sql: str, **params: Any) -> Any:
        with self.engine.connect() as conn:
            return conn.scalar(text(sql), params)


@pytest.fixture
def db(test_engine: Engine) -> Factory:
    _reset(test_engine)
    return Factory(test_engine)


class CapturingNotifier:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    async def send_password_reset(self, *, email: str, display_name: str, reset_url: str) -> None:
        self.sent.append({"email": email, "reset_url": reset_url})


@pytest.fixture
def api_app(db: Factory) -> FastAPI:
    app = create_app(make_settings())
    app.state.rate_limiter = InMemoryRateLimiter()
    app.state.reset_notifier = CapturingNotifier()
    return app


@pytest.fixture
def new_client(api_app: FastAPI) -> Callable[[], TestClient]:
    """Factory for independent browser-like clients (separate cookie jars) on one app."""
    clients: list[TestClient] = []

    def _make() -> TestClient:
        c = TestClient(api_app, raise_server_exceptions=False, backend_options=BACKEND_OPTIONS)
        c.__enter__()
        clients.append(c)
        return c

    yield _make  # type: ignore[misc]
    for c in clients:
        c.__exit__(None, None, None)


def login(client: TestClient, email: str, password: str = TEST_PASSWORD) -> TestClient:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    sync_csrf(client)
    return client


def sync_csrf(client: TestClient) -> None:
    """Mimic the frontend: echo the readable CSRF cookie in the request header."""
    token = client.cookies.get(CSRF_COOKIE)
    if token:
        client.headers[CSRF_HEADER] = token
    else:
        client.headers.pop(CSRF_HEADER, None)


@pytest.fixture
def as_user(db: Factory, new_client: Callable[[], TestClient]) -> Callable[..., TestClient]:
    """Create a user with roles and return a logged-in client for them."""

    def _as(
        roles: list[str], *, email: str | None = None, department_id: uuid.UUID | None = None
    ) -> TestClient:
        address = (
            email
            or f"{'-'.join(r.lower() for r in roles) or 'none'}-{uuid.uuid4().hex[:6]}@example.com"
        )
        db.user(address, roles, department_id=department_id)
        return login(new_client(), address)

    return _as


def run(coro: Any) -> Any:
    """Run a coroutine on a selector loop (Windows-safe) for service-level tests."""
    with asyncio.Runner(loop_factory=selector_event_loop) as runner:
        return runner.run(coro)
