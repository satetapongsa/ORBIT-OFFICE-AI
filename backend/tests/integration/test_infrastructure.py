"""Integration tests against real PostgreSQL/pgvector, Redis and MinIO.

Run with the Compose stack up and migrations applied::

    AURA_RUN_INTEGRATION=1 pytest -m integration
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import Settings
from app.main import create_app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("AURA_RUN_INTEGRATION") != "1",
        reason="set AURA_RUN_INTEGRATION=1 with the Compose stack running",
    ),
]


def test_readiness_all_dependencies_ok() -> None:
    settings = Settings(environment="test", storage_auto_create_bucket=True)
    with TestClient(create_app(settings)) as client:  # runs lifespan → creates bucket
        response = client.get("/api/v1/health")
    body = response.json()
    assert response.status_code == 200, body
    statuses = {c["name"]: c["status"] for c in body["components"]}
    assert statuses["database"] == "ok"
    assert statuses["redis"] == "ok"
    assert statuses["object_storage"] == "ok"


def test_migrations_applied_and_pgvector_usable() -> None:
    engine = create_engine(Settings().sync_database_url)
    with engine.connect() as conn:
        version = conn.scalar(text("SELECT version_num FROM alembic_version"))
        assert version is not None
        distance = conn.scalar(text("SELECT '[1,0,0]'::vector <=> '[0,1,0]'::vector"))
        assert distance == pytest.approx(1.0)
    engine.dispose()
