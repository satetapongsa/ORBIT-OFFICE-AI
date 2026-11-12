"""First administrator for a new installation (``python -m app.cli create-admin``).

Production refuses ``seed-dev``; this creates one real account with the ADMIN and EMPLOYEE
roles so the organisation can be set up from the web UI. The password is read from stdin
(never from the command line, where it would land in shell history and process lists) and
must pass the normal password policy.
"""

from __future__ import annotations

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.permissions import SystemRole
from app.core.security import hash_password, utcnow
from app.models.identity import Role, User, UserRole
from app.services.audit import AuditAction, record
from app.services.passwords import validate_new_password


class BootstrapError(Exception):
    pass


def create_admin(
    session: Session,
    settings: Settings,
    *,
    email: str,
    first_name: str,
    last_name: str,
    employee_code: str,
    password: str,
) -> User:
    try:
        address = validate_email(email, check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise BootstrapError(f"invalid e-mail: {exc}") from None
    if session.scalar(select(User.id).where(func.lower(User.email) == address)) is not None:
        raise BootstrapError(f"{address} already exists")
    if session.scalar(select(User.id).where(User.employee_code == employee_code)) is not None:
        raise BootstrapError(f"employee code {employee_code} already exists")
    validate_new_password(settings, password, email=address, field="password")

    roles = {
        r.code: r
        for r in session.scalars(
            select(Role).where(Role.code.in_([SystemRole.ADMIN.value, SystemRole.EMPLOYEE.value]))
        )
    }
    if len(roles) != 2:
        raise BootstrapError("system roles are missing; run `python -m app.cli sync-rbac` first")
    user = User(
        employee_code=employee_code,
        email=address,
        password_hash=hash_password(password),
        first_name=first_name,
        last_name=last_name,
        display_name=f"{first_name} {last_name}",
        is_active=True,
        password_changed_at=utcnow().replace(microsecond=0),
    )
    user.role_links = [UserRole(role_id=role.id) for role in roles.values()]
    session.add(user)
    session.flush()
    record(
        session,
        AuditAction.USER_CREATED,
        actor_id=None,
        entity_type="user",
        entity_id=user.id,
        details={"via": "cli:create-admin", "roles": sorted(roles)},
    )
    session.commit()
    return user
