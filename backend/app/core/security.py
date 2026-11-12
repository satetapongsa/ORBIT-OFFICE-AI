"""Password hashing, token creation/verification and CSRF helpers."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings

ACCESS_COOKIE = "orbit_access"
REFRESH_COOKIE = "orbit_refresh"
CSRF_COOKIE = "orbit_csrf"
CSRF_HEADER = "X-CSRF-Token"
ACCESS_COOKIE_PATH = "/api"
REFRESH_COOKIE_PATH = "/api/v1/auth"

_JWT_ALGORITHM = "HS256"
_password_hasher = PasswordHasher()  # Argon2id with library defaults (≥ OWASP minimum)

# A real-looking hash used to keep timing similar when the account does not exist.
_DUMMY_HASH = _password_hasher.hash(secrets.token_urlsafe(16))


def utcnow() -> datetime:
    return datetime.now(UTC)


# --- Passwords --------------------------------------------------------------------------


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-effort verification; also burns time when ``password_hash`` is missing."""
    try:
        return _password_hasher.verify(password_hash or _DUMMY_HASH, password) and bool(
            password_hash
        )
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _password_hasher.check_needs_rehash(password_hash)


# --- Opaque tokens (refresh, password reset, CSRF) --------------------------------------


def new_opaque_token() -> str:
    return secrets.token_urlsafe(32)  # 256 bits


def hash_token(token: str) -> str:
    """SHA-256 hex digest; opaque tokens are only ever stored hashed."""
    return hashlib.sha256(token.encode()).hexdigest()


def tokens_match(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return hmac.compare_digest(a.encode(), b.encode())


# --- Access tokens (JWT) ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    session_family_id: uuid.UUID
    issued_at: datetime
    expires_at: datetime


class InvalidTokenError(Exception):
    """Raised for any access token that is malformed, expired or not ours."""


def create_access_token(
    settings: Settings, *, user_id: uuid.UUID, session_family_id: uuid.UUID
) -> tuple[str, datetime]:
    now = utcnow()
    expires_at = now + timedelta(minutes=settings.access_token_ttl_minutes)
    payload: dict[str, Any] = {
        "iss": settings.jwt_issuer,
        "sub": str(user_id),
        "sid": str(session_family_id),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": secrets.token_hex(8),
    }
    token = jwt.encode(
        payload, settings.jwt_secret_key.get_secret_value(), algorithm=_JWT_ALGORITHM
    )
    return token, expires_at


def decode_access_token(settings: Settings, token: str) -> AccessTokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[_JWT_ALGORITHM],
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "sid", "iss"]},
        )
        if payload.get("type") != "access":
            raise InvalidTokenError("wrong token type")
        return AccessTokenClaims(
            user_id=uuid.UUID(payload["sub"]),
            session_family_id=uuid.UUID(payload["sid"]),
            issued_at=datetime.fromtimestamp(payload["iat"], UTC),
            expires_at=datetime.fromtimestamp(payload["exp"], UTC),
        )
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise InvalidTokenError(str(exc)) from exc
