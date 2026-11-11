"""Transactional email through SMTP (TRD 8.2, B2): invitations and password-reset links only.

Local development and tests deliver to Mailpit (SMTP 127.0.0.1:1025, no authentication);
production uses the same interface with a provider's SMTP relay, selected by settings only.
Nothing here can address an insurer: the only recipients are the product's own users.
"""

from __future__ import annotations

import smtplib
import ssl
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Protocol

from sp_core.settings import Settings
from sp_obs import get_logger

__all__ = ["Mailer", "SmtpMailer", "send_in_background"]

log = get_logger("sp_api.mail")


class Mailer(Protocol):
    def send(self, *, to: str, subject: str, body: str) -> None: ...


class SmtpMailer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, *, to: str, subject: str, body: str) -> None:
        s = self.settings
        msg = EmailMessage()
        msg["From"] = s.smtp_from
        msg["To"] = to
        msg["Subject"] = subject
        msg["Message-ID"] = make_msgid(domain="supplementpacket.test")
        msg.set_content(body)
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds) as smtp:
            if s.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if s.smtp_username and s.smtp_password:
                smtp.login(s.smtp_username, s.smtp_password)
            smtp.send_message(msg)
        log.info("email sent", extra={"subject_kind": subject.split(":", 1)[0]})  # never the address or the link


_BACKGROUND = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mail")


def send_in_background(mailer: Mailer, *, to: str, subject: str, body: str) -> None:
    """Send after the request: response time and errors do not depend on the SMTP round trip (B2-S04)."""

    def run() -> None:
        try:
            mailer.send(to=to, subject=subject, body=body)
        except Exception:  # noqa: BLE001 - logged, never raised into a request
            log.warning("email not sent", extra={"subject_kind": subject.split(":", 1)[0]})

    _BACKGROUND.submit(run)
