"""Audit logging. Records are added to the caller's transaction (committed with the change)."""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.principal import RequestMeta
from app.models.audit import AuditLog

# Keys that must never be stored in audit metadata.
_FORBIDDEN_KEYS = frozenset({"password", "new_password", "current_password", "token", "secret"})


class AuditAction(StrEnum):
    LOGIN = "auth.login"
    LOGIN_FAILED = "auth.login_failed"
    LOGIN_RATE_LIMITED = "auth.login_rate_limited"
    LOGOUT = "auth.logout"
    REFRESH_REUSE_DETECTED = "auth.refresh_reuse_detected"
    PASSWORD_CHANGED = "auth.password_changed"  # noqa: S105 - audit action name
    PASSWORD_RESET_REQUESTED = "auth.password_reset_requested"  # noqa: S105
    PASSWORD_RESET_COMPLETED = "auth.password_reset_completed"  # noqa: S105
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DEACTIVATED = "user.deactivated"
    USER_ACTIVATED = "user.activated"
    USER_ROLES_CHANGED = "user.roles_changed"
    ROLE_CREATED = "role.created"
    ROLE_UPDATED = "role.updated"
    ROLE_DELETED = "role.deleted"
    ROLE_PERMISSIONS_CHANGED = "role.permissions_changed"
    DEPARTMENT_CREATED = "department.created"
    DEPARTMENT_UPDATED = "department.updated"
    DEPARTMENT_DELETED = "department.deleted"
    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_VERSION_UPLOADED = "document.version_uploaded"
    DOCUMENT_UPDATED = "document.updated"
    DOCUMENT_DELETED = "document.deleted"
    DOCUMENT_DOWNLOADED = "document.downloaded"
    DOCUMENT_ACL_CHANGED = "document.acl_changed"
    DOCUMENT_REPROCESS_REQUESTED = "document.reprocess_requested"
    TASK_CREATED = "task.created"
    TASK_UPDATED = "task.updated"
    TASK_STATUS_CHANGED = "task.status_changed"
    TASK_ASSIGNEES_CHANGED = "task.assignees_changed"
    TASK_DELETED = "task.deleted"
    TASK_ATTACHMENT_ADDED = "task.attachment_added"
    TASK_ATTACHMENT_REMOVED = "task.attachment_removed"
    TASK_ATTACHMENT_DOWNLOADED = "task.attachment_downloaded"
    EMPLOYEE_HR_PROFILE_VIEWED = "employee.hr_profile_viewed"
    EMPLOYEE_HR_PROFILE_UPDATED = "employee.hr_profile_updated"
    AI_ACTION_CONFIRMED = "ai.action_confirmed"
    AI_ACTION_REJECTED = "ai.action_rejected"
    TICKET_CREATED = "ticket.created"
    TICKET_STATUS_CHANGED = "ticket.status_changed"
    TICKET_ASSIGNED = "ticket.assigned"
    TICKET_UPDATED = "ticket.updated"
    REPORT_EXPORTED = "report.exported"


def record(
    session: AsyncSession,
    action: AuditAction,
    *,
    actor_id: uuid.UUID | None,
    meta: RequestMeta | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    clean = {k: v for k, v in (details or {}).items() if k not in _FORBIDDEN_KEYS}
    entry = AuditLog(
        actor_id=actor_id,
        action=action.value,
        entity_type=entity_type,
        entity_id=entity_id,
        ip_address=meta.ip_address if meta else None,
        user_agent=(meta.user_agent or "")[:500] or None if meta else None,
        request_id=meta.request_id if meta else None,
        details=clean,
    )
    session.add(entry)
    return entry
