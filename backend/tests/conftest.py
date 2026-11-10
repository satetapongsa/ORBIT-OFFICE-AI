"""Shared pytest fixtures."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Make sure importing app.main never picks up a developer's .env or production values.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("STORAGE_AUTO_CREATE_BUCKET", "false")

from app.core.config import Settings
from app.main import create_app


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
    yield TestClient(app_factory(), raise_server_exceptions=False)
