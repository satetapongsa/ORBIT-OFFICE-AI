"""Outgoing e-mail over SMTP (standard library; called from the worker or a thread).

Disabled unless ``SMTP_HOST`` is set. In local development the Compose stack routes mail to
Mailpit (http://127.0.0.1:8025), so nothing leaves the machine.
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class MailError(Exception):
    pass


def mail_enabled(settings: Settings) -> bool:
    return bool(settings.smtp_host)


def send_mail(settings: Settings, *, to: str, subject: str, text: str) -> None:
    if not settings.smtp_host:
        raise MailError("SMTP is not configured")
    name, address = parseaddr(settings.smtp_from)
    message = EmailMessage()
    message["From"] = formataddr((name, address))
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    try:
        if settings.smtp_ssl:
            client: smtplib.SMTP = smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=20,
                context=ssl.create_default_context(),
            )
        else:
            client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
        with client:
            if settings.smtp_starttls and not settings.smtp_ssl:
                client.starttls(context=ssl.create_default_context())
            if settings.smtp_username and settings.smtp_password:
                client.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        # Never log the message body (it may contain a reset link).
        logger.warning("mail_send_failed", error_type=type(exc).__name__)
        raise MailError(type(exc).__name__) from None
