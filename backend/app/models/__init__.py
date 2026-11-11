"""ORM models. Import every model module here so Alembic autogenerate sees all tables."""

from app.models.audit import AuditLog
from app.models.auth import PasswordResetToken, UserSession
from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.document import (
    AccessLevel,
    Document,
    DocumentAcl,
    DocumentCategory,
    DocumentStatus,
    DocumentVersion,
    DocumentVersionText,
    DocumentVisibility,
    FileType,
    PrincipalType,
    ProcessingStatus,
)
from app.models.identity import (
    Department,
    EmploymentStatus,
    Permission,
    Role,
    User,
    UserRole,
    role_permissions,
)
from app.models.notification import Notification, NotificationType

__all__ = [
    "AccessLevel",
    "AuditLog",
    "Base",
    "Department",
    "Document",
    "DocumentAcl",
    "DocumentCategory",
    "DocumentStatus",
    "DocumentVersion",
    "DocumentVersionText",
    "DocumentVisibility",
    "EmploymentStatus",
    "FileType",
    "Notification",
    "NotificationType",
    "PasswordResetToken",
    "Permission",
    "PrincipalType",
    "ProcessingStatus",
    "Role",
    "SoftDeleteMixin",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "User",
    "UserRole",
    "UserSession",
    "role_permissions",
]
