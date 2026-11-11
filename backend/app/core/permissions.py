"""Permission catalogue and default system roles.

Permissions are defined in code (so endpoints can reference them safely) and synced to the
``permissions`` table by ``python -m app.cli sync-rbac``. Roles are database rows: the system
roles below are created/updated by the same command, and administrators can add new roles
with any subset of permissions without code changes.
"""

from __future__ import annotations

from enum import StrEnum


class P(StrEnum):
    """Permission codes (``domain:action``)."""

    USERS_READ = "users:read"
    USERS_CREATE = "users:create"
    USERS_UPDATE = "users:update"
    USERS_DEACTIVATE = "users:deactivate"

    DEPARTMENTS_READ = "departments:read"
    DEPARTMENTS_MANAGE = "departments:manage"

    ROLES_READ = "roles:read"
    ROLES_MANAGE = "roles:manage"
    ROLES_ASSIGN = "roles:assign"

    DOCUMENTS_READ = "documents:read"
    DOCUMENTS_UPLOAD = "documents:upload"
    DOCUMENTS_MANAGE = "documents:manage"
    DOCUMENTS_DELETE = "documents:delete"
    DOCUMENTS_MANAGE_ACCESS = "documents:manage_access"

    TASKS_READ_OWN = "tasks:read_own"
    TASKS_CREATE = "tasks:create"
    TASKS_READ_DEPARTMENT = "tasks:read_department"
    TASKS_ASSIGN = "tasks:assign"
    TASKS_MANAGE_DEPARTMENT = "tasks:manage_department"
    TASKS_MANAGE_ALL = "tasks:manage_all"

    EMPLOYEES_READ_DIRECTORY = "employees:read_directory"
    EMPLOYEES_READ_SENSITIVE = "employees:read_sensitive"
    EMPLOYEES_MANAGE = "employees:manage"

    TICKETS_CREATE = "tickets:create"
    TICKETS_READ_OWN = "tickets:read_own"
    TICKETS_READ_ALL = "tickets:read_all"
    TICKETS_ASSIGN = "tickets:assign"
    TICKETS_MANAGE = "tickets:manage"
    TICKETS_COMMENT_INTERNAL = "tickets:comment_internal"

    ANALYTICS_READ_OWN = "analytics:read_own"
    ANALYTICS_READ_DEPARTMENT = "analytics:read_department"
    ANALYTICS_READ_ALL = "analytics:read_all"
    REPORTS_EXPORT = "reports:export"

    AI_CHAT = "ai:chat"
    AI_USE_TOOLS = "ai:use_tools"

    SYSTEM_CONFIGURE = "system:configure"
    SYSTEM_CONFIGURE_AI = "system:configure_ai"

    AUDIT_READ = "audit:read"


PERMISSION_DESCRIPTIONS: dict[P, str] = {
    P.USERS_READ: "ดูรายชื่อและข้อมูลบัญชีผู้ใช้",
    P.USERS_CREATE: "สร้างบัญชีผู้ใช้",
    P.USERS_UPDATE: "แก้ไขข้อมูลบัญชีผู้ใช้",
    P.USERS_DEACTIVATE: "ระงับหรือเปิดใช้งานบัญชีผู้ใช้",
    P.DEPARTMENTS_READ: "ดูข้อมูลแผนก",
    P.DEPARTMENTS_MANAGE: "สร้าง แก้ไข และลบแผนก",
    P.ROLES_READ: "ดูบทบาทและสิทธิ์",
    P.ROLES_MANAGE: "สร้างและแก้ไขบทบาทและสิทธิ์",
    P.ROLES_ASSIGN: "กำหนดบทบาทให้ผู้ใช้",
    P.DOCUMENTS_READ: "ดูเอกสารที่มีสิทธิ์เข้าถึง",
    P.DOCUMENTS_UPLOAD: "อัปโหลดเอกสาร",
    P.DOCUMENTS_MANAGE: "จัดการเอกสารทั้งหมด",
    P.DOCUMENTS_DELETE: "ลบเอกสาร",
    P.DOCUMENTS_MANAGE_ACCESS: "กำหนดสิทธิ์การเข้าถึงเอกสาร",
    P.TASKS_READ_OWN: "ดูงานของตนเอง",
    P.TASKS_CREATE: "สร้างงาน",
    P.TASKS_READ_DEPARTMENT: "ดูงานของแผนก",
    P.TASKS_ASSIGN: "มอบหมายงาน",
    P.TASKS_MANAGE_DEPARTMENT: "จัดการงานของแผนก",
    P.TASKS_MANAGE_ALL: "จัดการงานทั้งหมด",
    P.EMPLOYEES_READ_DIRECTORY: "ดูสมุดรายชื่อพนักงาน",
    P.EMPLOYEES_READ_SENSITIVE: "ดูข้อมูลบุคคลที่เป็นความลับ",
    P.EMPLOYEES_MANAGE: "จัดการข้อมูลพนักงาน",
    P.TICKETS_CREATE: "แจ้งปัญหาไอที",
    P.TICKETS_READ_OWN: "ดูรายการแจ้งปัญหาของตนเอง",
    P.TICKETS_READ_ALL: "ดูรายการแจ้งปัญหาทั้งหมด",
    P.TICKETS_ASSIGN: "มอบหมายรายการแจ้งปัญหา",
    P.TICKETS_MANAGE: "จัดการสถานะรายการแจ้งปัญหา",
    P.TICKETS_COMMENT_INTERNAL: "เขียนบันทึกภายในของทีมไอที",
    P.ANALYTICS_READ_OWN: "ดูสถิติของตนเอง",
    P.ANALYTICS_READ_DEPARTMENT: "ดูรายงานของแผนก",
    P.ANALYTICS_READ_ALL: "ดูรายงานทั้งองค์กร",
    P.REPORTS_EXPORT: "ส่งออกรายงาน",
    P.AI_CHAT: "ใช้งานผู้ช่วย AI",
    P.AI_USE_TOOLS: "ให้ผู้ช่วย AI ใช้เครื่องมือของระบบ",
    P.SYSTEM_CONFIGURE: "ตั้งค่าระบบ",
    P.SYSTEM_CONFIGURE_AI: "ตั้งค่าผู้ให้บริการ AI",
    P.AUDIT_READ: "ดูบันทึกการใช้งานระบบ (Audit log)",
}

ALL_PERMISSIONS: frozenset[P] = frozenset(P)


class SystemRole(StrEnum):
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    EMPLOYEE = "EMPLOYEE"
    HR = "HR"
    IT_SUPPORT = "IT_SUPPORT"


_EMPLOYEE: frozenset[P] = frozenset(
    {
        P.DEPARTMENTS_READ,
        P.DOCUMENTS_READ,
        P.DOCUMENTS_UPLOAD,
        P.TASKS_READ_OWN,
        P.TASKS_CREATE,
        P.EMPLOYEES_READ_DIRECTORY,
        P.TICKETS_CREATE,
        P.TICKETS_READ_OWN,
        P.ANALYTICS_READ_OWN,
        P.AI_CHAT,
        P.AI_USE_TOOLS,
    }
)

SYSTEM_ROLES: dict[SystemRole, tuple[str, str, frozenset[P]]] = {
    SystemRole.ADMIN: ("ผู้ดูแลระบบ", "สิทธิ์ทั้งหมดของระบบ", ALL_PERMISSIONS),
    SystemRole.EMPLOYEE: ("พนักงาน", "สิทธิ์พื้นฐานของพนักงานทุกคน", _EMPLOYEE),
    SystemRole.MANAGER: (
        "ผู้จัดการ",
        "ดูแลงานและรายงานของทีม",
        _EMPLOYEE
        | {
            P.USERS_READ,
            P.TASKS_READ_DEPARTMENT,
            P.TASKS_ASSIGN,
            P.TASKS_MANAGE_DEPARTMENT,
            P.ANALYTICS_READ_DEPARTMENT,
            P.REPORTS_EXPORT,
        },
    ),
    SystemRole.HR: (
        "ฝ่ายบุคคล",
        "จัดการข้อมูลพนักงานและนโยบายบริษัท",
        _EMPLOYEE
        | {
            P.USERS_READ,
            P.USERS_CREATE,
            P.USERS_UPDATE,
            P.DEPARTMENTS_MANAGE,
            P.EMPLOYEES_READ_SENSITIVE,
            P.EMPLOYEES_MANAGE,
        },
    ),
    SystemRole.IT_SUPPORT: (
        "ฝ่ายไอที",
        "จัดการรายการแจ้งปัญหาไอที",
        _EMPLOYEE
        | {
            P.USERS_READ,
            P.TICKETS_READ_ALL,
            P.TICKETS_ASSIGN,
            P.TICKETS_MANAGE,
            P.TICKETS_COMMENT_INTERNAL,
        },
    ),
}

# Roles whose permission sets are fixed by code (cannot be edited through the API).
LOCKED_ROLES: frozenset[str] = frozenset({SystemRole.ADMIN.value})
