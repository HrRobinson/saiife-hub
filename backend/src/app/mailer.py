"""Outbound email behind a seam so tests never touch the network."""
from __future__ import annotations

from typing import Protocol

import httpx
import structlog

from .core.config import settings

log = structlog.get_logger(__name__)


class Mailer(Protocol):
    async def send_verification(self, email: str, link: str) -> None: ...


class ConsoleMailer:
    """Dev/test default: logs the link instead of sending it."""

    async def send_verification(self, email: str, link: str) -> None:
        log.info("verification_email", to=email, link=link)


class MailgunMailer:
    def __init__(self, api_key: str, domain: str, sender: str, base_url: str) -> None:
        self._api_key = api_key
        self._domain = domain
        self._sender = sender
        self._base_url = base_url.rstrip("/")

    async def send_verification(self, email: str, link: str) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{self._base_url}/v3/{self._domain}/messages",
                auth=("api", self._api_key),
                data={
                    "from": self._sender,
                    "to": email,
                    "subject": "Verify your saiife account",
                    "text": f"Confirm your email address:\n\n{link}\n\nThis link expires in 24 hours.",
                },
            )
            resp.raise_for_status()


_mailer: Mailer = ConsoleMailer()


def get_mailer() -> Mailer:
    return _mailer


def set_mailer(m: Mailer) -> None:
    global _mailer
    _mailer = m


def configure_default_mailer() -> None:
    """Use Mailgun only when BOTH key and domain are configured."""
    if settings.MAILGUN_API_KEY and settings.MAILGUN_DOMAIN:
        set_mailer(
            MailgunMailer(
                settings.MAILGUN_API_KEY,
                settings.MAILGUN_DOMAIN,
                settings.MAILGUN_FROM,
                settings.MAILGUN_BASE_URL,
            )
        )
    else:
        set_mailer(ConsoleMailer())
