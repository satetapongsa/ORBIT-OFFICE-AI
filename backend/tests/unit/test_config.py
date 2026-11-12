from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import (
    DEV_JWT_SECRET_PLACEHOLDER,
    DEV_STORAGE_SECRET_PLACEHOLDER,
    AIProvider,
    Settings,
)


def test_defaults_are_development_safe(settings_factory: Callable[..., Settings]) -> None:
    settings = settings_factory()
    assert settings.ai_chat_provider is AIProvider.DISABLED
    assert settings.cors_origins == []
    assert settings.docs_enabled is True


def test_cors_origins_parsed_from_csv(settings_factory: Callable[..., Settings]) -> None:
    settings = settings_factory(cors_origins="http://a.test, http://b.test")
    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_cors_wildcard_rejected(settings_factory: Callable[..., Settings]) -> None:
    with pytest.raises(ValidationError, match="explicit allow-list"):
        settings_factory(cors_origins="*")


# A complete, valid production configuration; tests change one value at a time. Every value is
# explicit so the container's development environment variables cannot leak in.
PRODUCTION: dict[str, Any] = {
    "environment": "production",
    "jwt_secret_key": "x" * 64,
    "storage_access_key": "prod-access-key",
    "storage_secret_key": "y" * 40,
    "database_url": "postgresql+psycopg://orbit:" + "z" * 32 + "@postgres:5432/orbit_office",
    "frontend_base_url": "https://office.example.com",
    "seed_dev_password": None,
    "cookie_secure": None,
    "debug": False,
    "log_json": None,
    "rate_limit_fail_open": None,
    "health_details_public": None,
    "proxy_shared_secret": None,
}


def test_production_with_strong_secrets(settings_factory: Callable[..., Settings]) -> None:
    settings = settings_factory(**PRODUCTION)
    assert settings.is_production
    assert settings.docs_enabled is False
    assert settings.use_json_logs is True
    assert settings.secure_cookies is True
    assert settings.rate_limit_fails_open is False
    assert settings.health_details_visible is False


def test_development_defaults_fail_open_and_show_health(
    settings_factory: Callable[..., Settings],
) -> None:
    settings = settings_factory(
        environment="development", rate_limit_fail_open=None, health_details_public=None
    )
    assert settings.rate_limit_fails_open is True
    assert settings.health_details_visible is True


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"jwt_secret_key": DEV_JWT_SECRET_PLACEHOLDER}, "JWT_SECRET_KEY"),
        ({"jwt_secret_key": "short"}, "JWT_SECRET_KEY"),
        ({"storage_secret_key": DEV_STORAGE_SECRET_PLACEHOLDER}, "STORAGE_SECRET_KEY"),
        ({"storage_access_key": "orbit-minio"}, "STORAGE_ACCESS_KEY"),
        (
            {"database_url": "postgresql+psycopg://orbit:orbit_dev_password@db:5432/orbit_office"},
            "DATABASE_URL",
        ),
        ({"cookie_secure": False}, "COOKIE_SECURE"),
        ({"frontend_base_url": "http://office.example.com"}, "FRONTEND_BASE_URL"),
        ({"seed_dev_password": "Some-Password-1"}, "SEED_DEV_PASSWORD"),
        ({"debug": True}, "DEBUG"),
        ({"proxy_shared_secret": "too-short"}, "PROXY_SHARED_SECRET"),
        ({"proxy_shared_secret": "CHANGE_ME" + "x" * 40}, "PROXY_SHARED_SECRET"),
    ],
)
def test_production_rejects_unsafe_values(
    settings_factory: Callable[..., Settings], override: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        settings_factory(**{**PRODUCTION, **override})


@pytest.mark.parametrize("scheme", ["postgres://", "postgresql://", "postgresql+psycopg://"])
def test_hosted_database_urls_use_psycopg(
    settings_factory: Callable[..., Settings], scheme: str
) -> None:
    settings = settings_factory(database_url=f"{scheme}u:p@db.example.com:5432/app")
    assert settings.sync_database_url == "postgresql+psycopg://u:p@db.example.com:5432/app"


def test_production_accepts_a_strong_proxy_secret(
    settings_factory: Callable[..., Settings],
) -> None:
    settings = settings_factory(**{**PRODUCTION, "proxy_shared_secret": "p" * 48})
    assert settings.proxy_shared_secret is not None


def test_chunk_overlap_must_be_smaller_than_chunk_size(
    settings_factory: Callable[..., Settings],
) -> None:
    with pytest.raises(ValidationError, match="RAG_CHUNK_OVERLAP"):
        settings_factory(rag_chunk_size=200, rag_chunk_overlap=200)


def test_anthropic_embeddings_rejected(settings_factory: Callable[..., Settings]) -> None:
    with pytest.raises(ValidationError, match="no embeddings"):
        settings_factory(ai_embedding_provider="anthropic")


def test_empty_env_values_are_treated_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_CHAT_PROVIDER", "anthropic")
    monkeypatch.setenv("AI_CHAT_MODEL", "claude-opus-5-5")
    monkeypatch.setenv("AI_CHAT_API_KEY", "")
    monkeypatch.setenv("CORS_ORIGINS", "")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.ai_chat_api_key is None
    assert settings.cors_origins == []


def test_secrets_not_exposed_in_repr(settings_factory: Callable[..., Settings]) -> None:
    settings = settings_factory(ai_chat_api_key="sk-test-should-not-leak")
    assert "sk-test-should-not-leak" not in repr(settings)
    assert "orbit_dev_password" not in repr(settings)
