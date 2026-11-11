"""ORM models. Import every model module here so Alembic autogenerate sees all tables."""

from app.models.ai import ActionStatus, AiActionRequest, ChatMessage, ChatRole, ChatSession
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
from app.models.employee import EmployeeHrProfile, EmploymentType
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
from app.models.task import (
    Task,
    TaskAssignee,
    TaskAttachment,
    TaskComment,
    TaskEvent,
    TaskEventType,
    TaskPriority,
    TaskStatus,
)

__all__ = [
    "AccessLevel",
    "ActionStatus",
    "AiActionRequest",
    "AuditLog",
    "Base",
    "ChatMessage",
    "ChatRole",
    "ChatSession",
    "Department",
    "Document",
    "DocumentAcl",
    "DocumentCategory",
    "DocumentStatus",
    "DocumentVersion",
    "DocumentVersionText",
    "DocumentVisibility",
    "EmployeeHrProfile",
    "EmploymentStatus",
    "EmploymentType",
    "FileType",
    "Notification",
    "NotificationType",
    "PasswordResetToken",
    "Permission",
    "PrincipalType",
    "ProcessingStatus",
    "Role",
    "SoftDeleteMixin",
    "Task",
    "TaskAssignee",
    "TaskAttachment",
    "TaskComment",
    "TaskEvent",
    "TaskEventType",
    "TaskPriority",
    "TaskStatus",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "User",
    "UserRole",
    "UserSession",
    "role_permissions",
]
