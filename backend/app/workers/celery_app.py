"""Celery application. Start a worker with::

    celery -A app.workers.celery_app worker --loglevel=INFO -Q default,documents

On Windows (local, non-Docker) add ``--pool=solo``.
"""

from __future__ import annotations

from celery import Celery
from celery.signals import setup_logging

from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()

celery_app = Celery(
    "orbit_office",
    broker=settings.broker_url,
    backend=settings.result_backend_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_default_queue="default",
    task_routes={"documents.*": {"queue": "documents"}},
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,  # tasks must be idempotent; redelivered if a worker dies
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=15 * 60,
    task_soft_time_limit=14 * 60,
    result_expires=24 * 3600,
    broker_connection_retry_on_startup=True,
)


@setup_logging.connect
def _configure_worker_logging(**_: object) -> None:
    configure_logging(get_settings())
