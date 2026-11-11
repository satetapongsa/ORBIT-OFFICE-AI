"""Idempotent synchronisation of the permission catalogue and system roles, plus dev seed data."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import ALL_PERMISSIONS, PERMISSION_DESCRIPTIONS, SYSTEM_ROLES, SystemRole
from app.core.security import hash_password, utcnow
from app.models.identity import Department, Permission, Role, User, UserRole


@dataclass
class SyncReport:
    permissions_created: list[str] = field(default_factory=list)
    roles_created: list[str] = field(default_factory=list)
    roles_updated: list[str] = field(default_factory=list)


def sync_rbac(session: Session) -> SyncReport:
    """Create missing permissions and make system roles match the code catalogue.

    Safe to run on every deploy. Custom (non-system) roles are never touched; permissions
    removed from code are kept in the table (and stay attached) until removed by a migration.
    """
    report = SyncReport()
    existing = {p.code: p for p in session.scalars(select(Permission))}
    for perm in sorted(ALL_PERMISSIONS):
        description = PERMISSION_DESCRIPTIONS.get(perm, "")
        if perm.value not in existing:
            row = Permission(code=perm.value, description=description)
            session.add(row)
            existing[perm.value] = row
            report.permissions_created.append(perm.value)
        elif existing[perm.value].description != description:
            existing[perm.value].description = description
    session.flush()

    roles = {r.code: r for r in session.scalars(select(Role))}
    for code, (name, description, perms) in SYSTEM_ROLES.items():
        wanted = [existing[p.value] for p in sorted(perms)]
        role = roles.get(code.value)
        if role is None:
            session.add(
                Role(
                    code=code.value,
                    name=name,
                    description=description,
                    is_system=True,
                    permissions=wanted,
                )
            )
            report.roles_created.append(code.value)
            continue
        current = {p.code for p in role.permissions}
        if current != {p.code for p in wanted} or role.name != name or not role.is_system:
            role.permissions = wanted
            role.name = name
            role.description = description
            role.is_system = True
            report.roles_updated.append(code.value)
    session.flush()
    return report


# --- Development seed -------------------------------------------------------------------

DEV_DEPARTMENTS = [
    ("ADM", "สำนักบริหาร"),
    ("HR", "ฝ่ายทรัพยากรบุคคล"),
    ("IT", "ฝ่ายเทคโนโลยีสารสนเทศ"),
    ("FIN", "ฝ่ายการเงินและบัญชี"),
    ("SALES", "ฝ่ายขาย"),
]

# (employee_code, email, first, last, department, roles, job title)
DEV_USERS = [
    (
        "DEV-0001",
        "admin@aura.example.com",
        "ผู้ดูแล",
        "ระบบ",
        "ADM",
        [SystemRole.ADMIN, SystemRole.EMPLOYEE],
        "ผู้ดูแลระบบ",
    ),
    (
        "DEV-0002",
        "manager@aura.example.com",
        "มานพ",
        "ผู้จัดการ",
        "SALES",
        [SystemRole.MANAGER, SystemRole.EMPLOYEE],
        "ผู้จัดการฝ่ายขาย",
    ),
    (
        "DEV-0003",
        "hr@aura.example.com",
        "หทัย",
        "บุคคล",
        "HR",
        [SystemRole.HR, SystemRole.EMPLOYEE],
        "เจ้าหน้าที่บุคคล",
    ),
    (
        "DEV-0004",
        "it@aura.example.com",
        "ไอรดา",
        "เทคโน",
        "IT",
        [SystemRole.IT_SUPPORT, SystemRole.EMPLOYEE],
        "เจ้าหน้าที่ไอที",
    ),
    (
        "DEV-0005",
        "employee@aura.example.com",
        "เอกชัย",
        "พนักงาน",
        "SALES",
        [SystemRole.EMPLOYEE],
        "พนักงานขาย",
    ),
]


def seed_dev(session: Session, password: str) -> list[str]:
    """Create development departments and one account per system role. Idempotent."""
    sync_rbac(session)
    depts = {
        d.code: d
        for d in session.scalars(select(Department).where(Department.deleted_at.is_(None)))
    }
    for code, name in DEV_DEPARTMENTS:
        if code not in depts:
            depts[code] = Department(code=code, name=name)
            session.add(depts[code])
    session.flush()

    roles = {r.code: r for r in session.scalars(select(Role))}
    created: list[str] = []
    password_hash = hash_password(password)
    for emp_code, email, first, last, dept, role_codes, title in DEV_USERS:
        if session.scalar(select(User.id).where(User.email == email)) is not None:
            continue
        user = User(
            employee_code=emp_code,
            email=email,
            password_hash=password_hash,
            first_name=first,
            last_name=last,
            display_name=f"{first} {last}",
            department_id=depts[dept].id,
            job_title=title,
            is_active=True,
            password_changed_at=utcnow().replace(microsecond=0),
        )
        user.role_links = [UserRole(role_id=roles[r.value].id) for r in role_codes]
        session.add(user)
        created.append(email)
    session.flush()
    if "SALES" in depts:
        manager = session.scalar(select(User).where(User.email == "manager@aura.example.com"))
        if manager and depts["SALES"].manager_id is None:
            depts["SALES"].manager_id = manager.id
    return created
