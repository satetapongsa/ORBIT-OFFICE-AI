"""Application settings loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.models.vector import EMBEDDING_DIMENSIONS

DEV_JWT_SECRET_PLACEHOLDER = "change-me-in-production-use-64-random-bytes"  # noqa: S105
DEV_STORAGE_SECRET_PLACEHOLDER = "orbit-minio-dev-secret"  # noqa: S105
DEV_DATABASE_PASSWORD = "orbit_dev_password"  # noqa: S105


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
    app_name: str = "ORBIT OFFICE AI"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool | None = None  # default: JSON everywhere except development
    api_docs_enabled: bool | None = None  # default: enabled except in production
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    # Business time zone: dashboards group activity by local calendar day in this zone.
    app_timezone: str = "Asia/Bangkok"

    # --- Security / authentication ---------------------------------------------------
    jwt_secret_key: SecretStr = SecretStr(DEV_JWT_SECRET_PLACEHOLDER)
    jwt_issuer: str = "orbit-office-ai"
    access_token_ttl_minutes: int = Field(default=15, ge=1, le=120)
    refresh_token_ttl_days: int = Field(default=7, ge=1, le=90)  # idle lifetime
    refresh_token_absolute_days: int = Field(default=30, ge=1, le=365)  # hard cap per login
    # A rotated refresh token re-presented within this window (parallel tabs) is rejected
    # without revoking the session; later re-use is treated as theft and revokes the family.
    refresh_reuse_grace_seconds: int = Field(default=10, ge=0, le=120)
    cookie_secure: bool | None = None  # default: Secure cookies except in development/test
    password_min_length: int = Field(default=12, ge=8, le=128)
    password_reset_ttl_minutes: int = Field(default=30, ge=5, le=1440)
    login_rate_limit_attempts: int = Field(default=10, ge=1)
    login_rate_limit_window_seconds: int = Field(default=900, ge=10)
    # When Redis is unreachable: allow requests (fail open) or refuse them with 503.
    # Default: open in development/test, closed in staging/production (ADR-049).
    rate_limit_fail_open: bool | None = None
    upload_rate_limit: int = Field(default=30, ge=1)  # uploads per user per window
    upload_rate_limit_window_seconds: int = Field(default=600, ge=10)
    export_rate_limit: int = Field(default=20, ge=1)  # report exports per user per window
    export_rate_limit_window_seconds: int = Field(default=600, ge=10)
    frontend_base_url: str = "http://127.0.0.1:3000"  # used in password-reset links
    # Password for development seed accounts (`python -m app.cli seed-dev`). Never used in prod.
    seed_dev_password: SecretStr | None = None

    # --- PostgreSQL ------------------------------------------------------------------
    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://orbit:orbit_dev_password@127.0.0.1:5432/orbit_office"
    )
    database_pool_size: int = Field(default=10, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)
    database_echo: bool = False
    # NullPool opens a connection per checkout; used by tests that create many event loops.
    database_use_null_pool: bool = False

    # --- Redis / Celery --------------------------------------------------------------
    redis_url: SecretStr = SecretStr("redis://127.0.0.1:6379/0")
    celery_broker_url: SecretStr | None = None  # defaults to redis_url
    celery_result_backend: SecretStr | None = None  # defaults to redis_url

    # --- Object storage (S3-compatible; MinIO locally) -------------------------------
    storage_endpoint_url: str | None = "http://127.0.0.1:9000"  # None = AWS S3 default
    storage_region: str = "us-east-1"
    storage_access_key: SecretStr = SecretStr("orbit-minio")
    storage_secret_key: SecretStr = SecretStr(DEV_STORAGE_SECRET_PLACEHOLDER)
    storage_bucket: str = "orbit-documents"
    storage_auto_create_bucket: bool = True  # convenience for local development only

    # --- Uploads (used from Phase 4) -------------------------------------------------
    upload_max_bytes: int = Field(default=25 * 1024 * 1024, ge=1)

    # --- AI provider (used from Phase 6) ---------------------------------------------
    ai_chat_provider: AIProvider = AIProvider.DISABLED
    ai_chat_model: str | None = None
    ai_chat_base_url: str | None = None
    ai_chat_api_key: SecretStr | None = None
    # Sent to openai_compatible servers only: current Claude models reject sampling parameters.
    ai_chat_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    ai_chat_max_tokens: int = Field(default=16000, ge=256, le=128000)
    ai_request_timeout_seconds: float = Field(default=120.0, gt=0)
    # Anthropic only: on a safety refusal the API re-runs the request on a fallback model
    # (server-side, models that support it). Disable to let refused requests simply stop.
    ai_chat_refusal_fallback: bool = True
    ai_chat_rate_limit_messages: int = Field(default=30, ge=1)
    ai_chat_rate_limit_window_seconds: int = Field(default=300, ge=10)
    ai_chat_history_messages: int = Field(default=40, ge=4, le=200)
    ai_chat_max_tool_steps: int = Field(default=6, ge=1, le=20)
    ai_action_ttl_minutes: int = Field(default=15, ge=1, le=1440)

    ai_embedding_provider: AIProvider = AIProvider.DISABLED
    ai_embedding_model: str | None = None
    ai_embedding_base_url: str | None = None
    ai_embedding_api_key: SecretStr | None = None
    ai_embedding_dimensions: int = Field(default=1024, ge=1, le=4096)

    rag_chunk_size: int = Field(default=1000, ge=100)  # characters
    rag_chunk_overlap: int = Field(default=150, ge=0)
    rag_top_k: int = Field(default=8, ge=1, le=50)
    ai_chat_retention_days: int = Field(default=180, ge=1)

    # --- E-mail (Phase 8; disabled while SMTP_HOST is empty) ------------------------
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str = "ORBIT OFFICE AI <no-reply@orbit.example.com>"
    smtp_starttls: bool = True
    smtp_ssl: bool = False

    # --- Health checks ---------------------------------------------------------------
    health_check_timeout_seconds: float = Field(default=3.0, gt=0)
    # Component details in GET /health (default: shown outside production only). Monitoring
    # can still read them in production with the header `X-Health-Token`.
    health_details_public: bool | None = None
    health_check_token: SecretStr | None = None

    # --- Hosted front end (Vercel) in front of a separately hosted API (ADR-055) -----
    # When set, every API request except the liveness probe must carry this value in the
    # `X-Orbit-Proxy-Secret` header (added by the front end's proxy), so the API cannot be
    # called around it and the client IP it reports can be trusted.
    proxy_shared_secret: SecretStr | None = None

    # --- Retention and clean-up (Phase 9, Celery beat + `python -m app.cli purge`) --
    document_purge_after_days: int = Field(default=30, ge=1)  # after soft delete
    storage_orphan_grace_hours: int = Field(default=24, ge=1)  # unreferenced objects
    session_purge_after_days: int = Field(default=30, ge=1)  # after expiry/revocation
    notification_retention_days: int = Field(default=365, ge=7)  # read notifications

    @field_validator("app_timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"APP_TIMEZONE {value!r} is not a valid IANA time zone") from None
        return value

    @field_validator("database_url", mode="before")
    @classmethod
    def _psycopg_driver(cls, value: object) -> object:
        """Hosted databases hand out `postgres://` or `postgresql://`; the app uses psycopg 3."""
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if isinstance(raw, str):
            for prefix in ("postgres://", "postgresql://"):
                if raw.startswith(prefix):
                    return SecretStr("postgresql+psycopg://" + raw[len(prefix) :])
        return value

    @field_validator("proxy_shared_secret", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

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
        if (
            self.ai_embedding_provider is not AIProvider.DISABLED
            and self.ai_embedding_dimensions != EMBEDDING_DIMENSIONS
        ):
            raise ValueError(
                f"AI_EMBEDDING_DIMENSIONS must be {EMBEDDING_DIMENSIONS} (the vector column size "
                "fixed by migration 0007); another size needs a new migration and a re-index."
            )
        if self.is_production:
            self._validate_production()
        return self

    def _validate_production(self) -> None:
        for name, value in (
            ("JWT_SECRET_KEY", self.jwt_secret_key),
            ("DATABASE_URL", self.database_url),
            ("REDIS_URL", self.redis_url),
            ("STORAGE_ACCESS_KEY", self.storage_access_key),
            ("STORAGE_SECRET_KEY", self.storage_secret_key),
        ):
            if "CHANGE_ME" in value.get_secret_value():
                raise ValueError(f"{name} still contains a CHANGE_ME placeholder")
        if self.health_check_token and "CHANGE_ME" in self.health_check_token.get_secret_value():
            raise ValueError("HEALTH_CHECK_TOKEN still contains a CHANGE_ME placeholder")
        if self.proxy_shared_secret is not None:
            proxy_secret = self.proxy_shared_secret.get_secret_value()
            if "CHANGE_ME" in proxy_secret or len(proxy_secret) < 32:
                raise ValueError(
                    "PROXY_SHARED_SECRET must be a strong random value (>= 32 chars) in production"
                )
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
        if f":{DEV_DATABASE_PASSWORD}@" in self.database_url.get_secret_value():
            raise ValueError("DATABASE_URL must not use the development password in production")
        if self.storage_access_key.get_secret_value() == "orbit-minio":
            raise ValueError(
                "STORAGE_ACCESS_KEY must not use the development default in production"
            )
        if self.cookie_secure is False:
            raise ValueError("COOKIE_SECURE cannot be false in production (HTTPS only)")
        if not self.frontend_base_url.startswith("https://"):
            raise ValueError("FRONTEND_BASE_URL must be an https:// URL in production")
        if self.seed_dev_password is not None:
            raise ValueError("SEED_DEV_PASSWORD must not be set in production")

    @property
    def is_production(self) -> bool:
        return self.environment in (Environment.PRODUCTION, Environment.STAGING)

    @property
    def rate_limit_fails_open(self) -> bool:
        if self.rate_limit_fail_open is not None:
            return self.rate_limit_fail_open
        return not self.is_production

    @property
    def health_details_visible(self) -> bool:
        if self.health_details_public is not None:
            return self.health_details_public
        return not self.is_production

    @property
    def secure_cookies(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.environment not in (Environment.DEVELOPMENT, Environment.TEST)

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
