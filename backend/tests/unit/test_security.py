from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import Settings
from app.core.errors import ValidationFailedError
from app.core.permissions import (
    ALL_PERMISSIONS,
    LOCKED_ROLES,
    PERMISSION_DESCRIPTIONS,
    SYSTEM_ROLES,
)
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    hash_token,
    tokens_match,
    verify_password,
)
from app.services.passwords import validate_new_password


def test_argon2id_hash_and_verify() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed.startswith("$argon2id$")
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong", hashed)
    assert not verify_password("anything", None)
    assert not verify_password("anything", "not-a-hash")


def test_access_token_round_trip(settings_factory: Callable[..., Settings]) -> None:
    settings = settings_factory()
    user_id, family = uuid.uuid4(), uuid.uuid4()
    token, expires_at = create_access_token(settings, user_id=user_id, session_family_id=family)
    claims = decode_access_token(settings, token)
    assert claims.user_id == user_id
    assert claims.session_family_id == family
    assert claims.expires_at == expires_at.replace(microsecond=0)


def test_access_token_rejects_other_secret_wrong_type_and_expiry(
    settings_factory: Callable[..., Settings],
) -> None:
    settings = settings_factory()
    token, _ = create_access_token(settings, user_id=uuid.uuid4(), session_family_id=uuid.uuid4())
    with pytest.raises(InvalidTokenError):
        decode_access_token(settings_factory(jwt_secret_key="another-secret-" + "x" * 40), token)

    now = datetime.now(UTC)
    base = {
        "iss": settings.jwt_issuer,
        "sub": str(uuid.uuid4()),
        "sid": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
    }
    secret = settings.jwt_secret_key.get_secret_value()
    refresh_type = jwt.encode(
        {**base, "type": "refresh", "exp": int((now + timedelta(minutes=5)).timestamp())},
        secret,
        "HS256",
    )
    expired = jwt.encode(
        {**base, "type": "access", "exp": int((now - timedelta(seconds=5)).timestamp())},
        secret,
        "HS256",
    )
    unsigned = jwt.encode(
        {**base, "type": "access", "exp": int((now + timedelta(minutes=5)).timestamp())},
        None,
        "none",
    )
    for bad in (refresh_type, expired, unsigned, "garbage"):
        with pytest.raises(InvalidTokenError):
            decode_access_token(settings, bad)


def test_opaque_token_helpers() -> None:
    assert len(hash_token("abc")) == 64
    assert tokens_match("same", "same")
    assert not tokens_match("same", "other")
    assert not tokens_match(None, "x")


def test_password_policy(settings_factory: Callable[..., Settings]) -> None:
    settings = settings_factory()
    validate_new_password(settings, "Long-And-Unique-42", email="somchai@example.com", field="p")
    for weak in ("short", "aaaaaaaaaaaaaaa", "somchai-is-my-pass", "password1234"):
        with pytest.raises(ValidationFailedError):
            validate_new_password(settings, weak, email="somchai@example.com", field="p")


def test_permission_catalogue_is_consistent() -> None:
    assert set(PERMISSION_DESCRIPTIONS) == set(ALL_PERMISSIONS)
    assert {r.value for r in SYSTEM_ROLES} == {"ADMIN", "MANAGER", "EMPLOYEE", "HR", "IT_SUPPORT"}
    admin_perms = SYSTEM_ROLES[next(r for r in SYSTEM_ROLES if r.value == "ADMIN")][2]
    assert admin_perms == ALL_PERMISSIONS
    assert "ADMIN" in LOCKED_ROLES
    for _, _, perms in SYSTEM_ROLES.values():
        assert perms <= ALL_PERMISSIONS
