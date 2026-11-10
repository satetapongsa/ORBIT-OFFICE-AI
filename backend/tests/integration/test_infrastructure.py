"""Integration tests against real PostgreSQL/pgvector, Redis and MinIO.

Run with the Compose stack up and migrations applied::

    AURA_RUN_INTEGRATION=1 pytest -m integration
"""

from __future__ import annotations

import os
import uuid

import pytest
import redis
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.config import Settings
from app.core.event_loop import selector_event_loop
from app.core.storage import ObjectStorage
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
    # Selector loop: async psycopg does not support Windows' default Proactor loop.
    backend_options = {"loop_factory": selector_event_loop}
    with TestClient(create_app(settings), backend_options=backend_options) as client:
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


def test_redis_set_get_round_trip() -> None:
    client = redis.Redis.from_url(Settings().redis_url.get_secret_value(), decode_responses=True)
    key = f"aura:integration-test:{uuid.uuid4()}"
    try:
        assert client.set(key, "ทดสอบ", ex=30)
        assert client.get(key) == "ทดสอบ"
    finally:
        client.delete(key)
        client.close()


def test_object_storage_put_get_delete_round_trip() -> None:
    storage = ObjectStorage(Settings())
    storage.ensure_bucket()
    s3 = storage._client  # upload/download helpers arrive with the Document Center (Phase 4)
    key = f"integration-tests/{uuid.uuid4()}.txt"
    payload = "เอกสารทดสอบ AURA".encode()
    s3.put_object(Bucket=storage.bucket, Key=key, Body=payload, ContentType="text/plain")
    try:
        fetched = s3.get_object(Bucket=storage.bucket, Key=key)["Body"].read()
        assert fetched == payload
    finally:
        s3.delete_object(Bucket=storage.bucket, Key=key)
    with pytest.raises(ClientError):
        s3.head_object(Bucket=storage.bucket, Key=key)


def test_celery_worker_ping_round_trip() -> None:
    from app.workers.tasks import ping

    result = ping.delay().get(timeout=30)
    assert result["status"] == "ok"
