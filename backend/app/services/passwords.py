"""Password policy."""

from __future__ import annotations

from app.core.config import Settings
from app.core.errors import ValidationFailedError
from app.schemas.common import ErrorDetail

_COMMON = frozenset(
    {
        "password1234",
        "password12345",
        "123456789012",
        "qwertyuiop12",
        "aaaaaaaaaaaa",
        "changeme1234",
        "welcome12345",
    }
)


def validate_new_password(settings: Settings, password: str, *, email: str, field: str) -> None:
    problems: list[str] = []
    if len(password) < settings.password_min_length:
        problems.append(f"รหัสผ่านต้องมีอย่างน้อย {settings.password_min_length} ตัวอักษร")
    if password.lower() in _COMMON or len(set(password)) < 4:
        problems.append("รหัสผ่านนี้คาดเดาง่ายเกินไป")
    local = email.split("@", 1)[0].lower()
    if len(local) >= 4 and local in password.lower():
        problems.append("รหัสผ่านต้องไม่มีชื่ออีเมลของคุณ")
    if problems:
        raise ValidationFailedError(
            "รหัสผ่านไม่เป็นไปตามนโยบาย",
            details=[ErrorDetail(field=field, message=p) for p in problems],
        )
