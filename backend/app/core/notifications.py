"""Delivery of security messages (password reset links).

With SMTP configured (``SMTP_HOST``) the link is e-mailed. Without it, in ``development`` the
link is written to the server log so the flow can be exercised locally; in every other
environment the link is **not** logged and a warning states that delivery is not configured.
"""

from __future__ import annotations

from typing import Protocol

from app.core.config import Environment, Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class PasswordResetNotifier(Protocol):
    async def send_password_reset(
        self, *, email: str, display_name: str, reset_url: str
    ) -> None: ...


class LogPasswordResetNotifier:
    def __init__(self, settings: Settings) -> None:
        self._dev = settings.environment is Environment.DEVELOPMENT

    async def send_password_reset(self, *, email: str, display_name: str, reset_url: str) -> None:
        if self._dev:
            logger.info("password_reset_link_dev_only", email=email, reset_url=reset_url)
        else:
            logger.warning("password_reset_delivery_not_configured")


class MailPasswordResetNotifier:
    """Sends the reset link by e-mail (in a thread; never logs the link)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send_password_reset(self, *, email: str, display_name: str, reset_url: str) -> None:
        import anyio

        from app.core.mail import MailError, send_mail

        minutes = self._settings.password_reset_ttl_minutes
        text = "\n".join(
            [
                f"เรียน คุณ{display_name}",
                "",
                "มีคำขอตั้งรหัสผ่านใหม่สำหรับบัญชี ORBIT OFFICE AI ของคุณ",
                f"กดลิงก์นี้ภายใน {minutes} นาทีเพื่อตั้งรหัสผ่านใหม่:",
                reset_url,
                "",
                "หากคุณไม่ได้ขอ ให้เพิกเฉยต่ออีเมลนี้ รหัสผ่านเดิมยังใช้ได้ตามปกติ",
            ]
        )
        try:
            await anyio.to_thread.run_sync(
                lambda: send_mail(
                    self._settings, to=email, subject="[ORBIT] ตั้งรหัสผ่านใหม่", text=text
                )
            )
        except MailError:
            logger.warning("password_reset_email_failed")


def build_reset_notifier(settings: Settings) -> PasswordResetNotifier:
    from app.core.mail import mail_enabled

    if mail_enabled(settings):
        return MailPasswordResetNotifier(settings)
    return LogPasswordResetNotifier(settings)
