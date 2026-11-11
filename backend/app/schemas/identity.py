"""Schemas for users, departments, roles, permissions and audit logs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

from app.models.identity import EmploymentStatus

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Code = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$"
    ),
]
RoleCode = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Z][A-Z0-9_]{1,49}$")
]
PermissionCode = Annotated[str, StringConstraints(pattern=r"^[a-z_]+:[a-z_]+$", max_length=100)]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Departments ------------------------------------------------------------------------


class DepartmentRef(ORMModel):
    id: uuid.UUID
    code: str
    name: str


class DepartmentOut(DepartmentRef):
    description: str | None
    parent_id: uuid.UUID | None
    manager_id: uuid.UUID | None
    member_count: int = 0
    created_at: datetime
    updated_at: datetime


class DepartmentCreate(BaseModel):
    code: Code
    name: ShortText = Field(min_length=1)
    description: str | None = Field(default=None, max_length=2000)
    parent_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None


class DepartmentUpdate(BaseModel):
    code: Code | None = None
    name: ShortText | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, max_length=2000)
    parent_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None


# --- Roles & permissions ----------------------------------------------------------------


class PermissionOut(ORMModel):
    code: str
    description: str


class RoleRef(ORMModel):
    id: uuid.UUID
    code: str
    name: str


class RoleOut(RoleRef):
    description: str
    is_system: bool
    is_locked: bool = False
    permissions: list[str]
    created_at: datetime
    updated_at: datetime


class RoleCreate(BaseModel):
    code: RoleCode
    name: ShortText = Field(min_length=1)
    description: str = Field(default="", max_length=500)
    permissions: list[PermissionCode] = Field(default_factory=list, max_length=200)


class RoleUpdate(BaseModel):
    name: ShortText | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, max_length=500)


class RolePermissionsUpdate(BaseModel):
    permissions: list[PermissionCode] = Field(max_length=200)


# --- Users ------------------------------------------------------------------------------


class UserOut(ORMModel):
    id: uuid.UUID
    employee_code: str
    email: str
    first_name: str
    last_name: str
    display_name: str
    department: DepartmentRef | None
    job_title: str | None
    phone_work: str | None
    employment_status: EmploymentStatus
    is_active: bool
    roles: list[RoleRef]
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    employee_code: Code
    email: EmailStr
    first_name: Name
    last_name: Name
    display_name: ShortText | None = None
    department_id: uuid.UUID | None = None
    job_title: ShortText | None = None
    phone_work: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = (
        None
    )
    employment_status: EmploymentStatus = EmploymentStatus.ACTIVE
    # Optional initial password. Without one the user sets a password via the reset flow.
    password: str | None = Field(default=None, max_length=256)
    role_codes: list[RoleCode] = Field(default_factory=lambda: ["EMPLOYEE"], max_length=20)


class UserUpdate(BaseModel):
    employee_code: Code | None = None
    email: EmailStr | None = None
    first_name: Name | None = None
    last_name: Name | None = None
    display_name: ShortText | None = None
    department_id: uuid.UUID | None = None
    job_title: ShortText | None = None
    phone_work: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = (
        None
    )
    employment_status: EmploymentStatus | None = None


class UserRolesUpdate(BaseModel):
    role_codes: list[RoleCode] = Field(max_length=20)


# --- Audit ------------------------------------------------------------------------------


class AuditLogOut(ORMModel):
    id: uuid.UUID
    occurred_at: datetime
    actor_id: uuid.UUID | None
    action: str
    entity_type: str | None
    entity_id: uuid.UUID | None
    ip_address: str | None
    user_agent: str | None
    request_id: str | None
    details: dict[str, Any]

    @field_validator("ip_address", mode="before")
    @classmethod
    def _ip_to_str(cls, value: object) -> object:
        return str(value) if value is not None else None
