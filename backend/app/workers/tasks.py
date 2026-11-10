"""Background tasks. Feature tasks (document processing, notifications) arrive in later phases."""

from __future__ import annotations

from datetime import UTC, datetime

from app.workers.celery_app import celery_app


@celery_app.task(name="system.ping")
def ping() -> dict[str, str]:
    """Round-trip check used to verify broker → worker → result backend wiring."""
    return {"status": "ok", "at": datetime.now(UTC).isoformat()}
