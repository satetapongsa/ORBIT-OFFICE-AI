"""Delivery of security messages (password reset links).

No mail provider is configured yet. In ``development`` the reset link is written to the
server log so the flow can be exercised locally; in every other environment the link is
**not** logged and a warning states that delivery is not configured. A real e-mail adapter
plugs in behind the same protocol later.
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
