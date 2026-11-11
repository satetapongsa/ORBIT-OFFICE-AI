"""Employee Center schemas.

Directory fields (work contact details) are visible to every holder of
``employees:read_directory``. Account fields need ``users:read``; HR fields live in a separate
response that needs ``employees:read_sensitive`` (or is your own).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, StringConstraints

from app.models.employee import EmploymentType
from app.models.identity import EmploymentStatus
from app.schemas.documents import UserRef
from app.schemas.identity import DepartmentRef, RoleRef

Phone = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
ShortName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class EmployeeListItem(BaseModel):
    id: uuid.UUID
    employee_code: str
    display_name: str
    first_name: str
    last_name: str
    job_title: str | None
    department: DepartmentRef | None
    email: str
    phone_work: str | None
    is_active: bool


class EmployeePage(BaseModel):
    items: list[EmployeeListItem]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class EmployeeAccount(BaseModel):
    """Account administration fields (``users:read``)."""

    employment_status: EmploymentStatus
    roles: list[RoleRef]
    last_login_at: datetime | None
    created_at: datetime


class EmployeeCapabilities(BaseModel):
    can_edit_account: bool
    can_manage_roles: bool
    can_change_active: bool
    can_view_hr: bool
    can_edit_hr: bool


class EmployeeProfile(EmployeeListItem):
    department_manager: UserRef | None
    account: EmployeeAccount | None
    capabilities: EmployeeCapabilities


class EmergencyContact(BaseModel):
    name: ShortName
    relationship: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]
    phone: Phone


class HrProfileIn(BaseModel):
    """Full replacement of the HR record. Only the last 4 digits of the national ID."""

    date_of_birth: date | None = None
    national_id_last4: Annotated[str, StringConstraints(pattern=r"^[0-9]{4}$")] | None = None
    personal_phone: Phone | None = None
    personal_email: EmailStr | None = None
    address: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None
    hire_date: date | None = None
    employment_type: EmploymentType | None = None
    emergency_contact: EmergencyContact | None = None


class HrProfileOut(HrProfileIn):
    user_id: uuid.UUID
    exists: bool
    updated_at: datetime | None
    updated_by: UserRef | None
