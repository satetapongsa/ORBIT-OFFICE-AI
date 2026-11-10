"""Application settings loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEV_JWT_SECRET_PLACEHOLDER = "change-me-in-production-use-64-random-bytes"  # noqa: S105
DEV_STORAGE_SECRET_PLACEHOLDER = "aura-minio-dev-secret"  # noqa: S105


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class AIProvider(StrEnum):
    """Supported AI provider adapters. ``DISABLED`` means no provider is configured."""

    DISABLED = "disabled"
    OPENAI_COMPATIBLE = "openai_compatible"  # Ollama, vLLM, LM Studio, OpenAI, gateways
    ANTHROPIC = "anthropic"  # chat only — Anthropic has no embeddings endpoint


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Repository-root .env (when run from backend/) and a local override; later wins.
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        # `AI_CHAT_API_KEY=` in a .env file means "unset", not "empty string".
        env_ignore_empty=True,
    )

    # --- Application -----------------------------------------------------------------
    app_name: str = "AURA OFFICE AI"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool | None = None  # default: JSON everywhere except development
    api_docs_enabled: bool | None = None  # default: enabled except in production
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # --- Security (used from Phase 2) ------------------------------------------------
    jwt_secret_key: SecretStr = SecretStr(DEV_JWT_SECRET_PLACEHOLDER)
    access_token_ttl_minutes: int = Field(default=15, ge=1, le=120)
    refresh_token_ttl_days: int = Field(default=7, ge=1, le=90)

    # --- PostgreSQL ------------------------------------------------------------------
    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://aura:aura_dev_password@localhost:5432/aura_office"
    )
    database_pool_size: int = Field(default=10, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)
    database_echo: bool = False

    # --- Redis / Celery --------------------------------------------------------------
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")
    celery_broker_url: SecretStr | None = None  # defaults to redis_url
    celery_result_backend: SecretStr | None = None  # defaults to redis_url

    # --- Object storage (S3-compatible; MinIO locally) -------------------------------
    storage_endpoint_url: str | None = "http://localhost:9000"  # None = AWS S3 default
    storage_region: str = "us-east-1"
    storage_access_key: SecretStr = SecretStr("aura-minio")
    storage_secret_key: SecretStr = SecretStr(DEV_STORAGE_SECRET_PLACEHOLDER)
    storage_bucket: str = "aura-documents"
    storage_auto_create_bucket: bool = True  # convenience for local development only

    # --- Uploads (used from Phase 4) -------------------------------------------------
    upload_max_bytes: int = Field(default=25 * 1024 * 1024, ge=1)

    # --- AI provider (used from Phase 6) ---------------------------------------------
    ai_chat_provider: AIProvider = AIProvider.DISABLED
    ai_chat_model: str | None = None
    ai_chat_base_url: str | None = None
    ai_chat_api_key: SecretStr | None = None
    ai_chat_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    ai_chat_max_tokens: int = Field(default=4096, ge=1)
    ai_request_timeout_seconds: float = Field(default=120.0, gt=0)

    ai_embedding_provider: AIProvider = AIProvider.DISABLED
    ai_embedding_model: str | None = None
    ai_embedding_base_url: str | None = None
    ai_embedding_api_key: SecretStr | None = None
    ai_embedding_dimensions: int = Field(default=1024, ge=1, le=4096)

    rag_chunk_size: int = Field(default=1000, ge=100)  # characters
    rag_chunk_overlap: int = Field(default=150, ge=0)
    rag_top_k: int = Field(default=8, ge=1, le=50)
    ai_chat_retention_days: int = Field(default=180, ge=1)

    # --- Health checks ---------------------------------------------------------------
    health_check_timeout_seconds: float = Field(default=3.0, gt=0)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _validate(self) -> Settings:
        if self.rag_chunk_overlap >= self.rag_chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP must be smaller than RAG_CHUNK_SIZE")
        if "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS must be an explicit allow-list; '*' is not allowed")
        if self.ai_embedding_provider is AIProvider.ANTHROPIC:
            raise ValueError(
                "AI_EMBEDDING_PROVIDER=anthropic is not supported: Anthropic has no embeddings "
                "API. Use openai_compatible (e.g. Ollama) for embeddings."
            )
        if self.is_production:
            self._validate_production()
        return self

    def _validate_production(self) -> None:
        secret = self.jwt_secret_key.get_secret_value()
        if secret == DEV_JWT_SECRET_PLACEHOLDER or len(secret) < 32:
            raise ValueError(
                "JWT_SECRET_KEY must be a strong random value (>= 32 chars) in production"
            )
        if self.storage_secret_key.get_secret_value() == DEV_STORAGE_SECRET_PLACEHOLDER:
            raise ValueError(
                "STORAGE_SECRET_KEY must not use the development default in production"
            )
        if self.debug:
            raise ValueError("DEBUG must be false in production")

    @property
    def is_production(self) -> bool:
        return self.environment in (Environment.PRODUCTION, Environment.STAGING)

    @property
    def use_json_logs(self) -> bool:
        if self.log_json is not None:
            return self.log_json
        return self.environment is not Environment.DEVELOPMENT

    @property
    def docs_enabled(self) -> bool:
        if self.api_docs_enabled is not None:
            return self.api_docs_enabled
        return not self.is_production

    @property
    def broker_url(self) -> str:
        return (self.celery_broker_url or self.redis_url).get_secret_value()

    @property
    def result_backend_url(self) -> str:
        return (self.celery_result_backend or self.redis_url).get_secret_value()

    @property
    def sync_database_url(self) -> str:
        """Same DSN; psycopg 3 serves both the async (API) and sync (Alembic, Celery) engines."""
        return self.database_url.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()
