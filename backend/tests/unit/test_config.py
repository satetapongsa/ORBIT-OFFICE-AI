from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from app.core.config import AIProvider, Settings


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


def test_production_rejects_default_jwt_secret(settings_factory: Callable[..., Settings]) -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        settings_factory(environment="production")


def test_production_rejects_default_storage_secret(
    settings_factory: Callable[..., Settings],
) -> None:
    with pytest.raises(ValidationError, match="STORAGE_SECRET_KEY"):
        settings_factory(environment="production", jwt_secret_key="x" * 64)


def test_production_with_strong_secrets(settings_factory: Callable[..., Settings]) -> None:
    settings = settings_factory(
        environment="production",
        jwt_secret_key="x" * 64,
        storage_secret_key="y" * 40,
        log_json=None,
    )
    assert settings.is_production
    assert settings.docs_enabled is False
    assert settings.use_json_logs is True


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
    assert "aura_dev_password" not in repr(settings)
