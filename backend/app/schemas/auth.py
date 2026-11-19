"""Authentication request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, StringConstraints

from app.schemas.identity import UserOut


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class SessionInfo(BaseModel):
    access_expires_at: datetime


class MeResponse(BaseModel):
    user: UserOut
    permissions: list[str]
    session: SessionInfo | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=1, max_length=256)


class MessageResponse(BaseModel):
    message: str


Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class RegistrationInfo(BaseModel):
    enabled: bool
    allowed_domains: list[str]


class RegisterRequest(BaseModel):
    email: EmailStr = Field(max_length=320)
    first_name: Name
    last_name: Name
    password: str = Field(min_length=1, max_length=256)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=20, max_length=200)
