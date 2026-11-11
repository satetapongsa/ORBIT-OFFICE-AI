"""Authenticated principal and request metadata passed from the API layer to services."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """The authenticated user for one request. Permissions are loaded fresh per request."""

    id: uuid.UUID
    email: str
    display_name: str
    department_id: uuid.UUID | None
    role_ids: frozenset[uuid.UUID]
    role_codes: frozenset[str]
    permissions: frozenset[str]
    session_family_id: uuid.UUID | None = None

    def has(self, permission: str) -> bool:
        return permission in self.permissions

    def has_all(self, permissions: Iterable[str]) -> bool:
        return set(permissions) <= self.permissions

    def has_any(self, permissions: Iterable[str]) -> bool:
        return bool(set(permissions) & self.permissions)


@dataclass(frozen=True, slots=True)
class RequestMeta:
    """Client details recorded in audit logs and sessions."""

    ip_address: str | None = None
    user_agent: str | None = None
    request_id: str | None = None
    extra: dict[str, str] = field(default_factory=dict)
