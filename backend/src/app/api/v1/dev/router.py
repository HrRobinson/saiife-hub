"""Dev-only helpers. Every handler refuses to run when ENV == "prod".

`RecordingMailer` keeps the last verification link per address in memory so the
Playwright e2e can complete the signup flow without a real inbox. Nothing here is
reachable in production, and it never exposes account tokens or password hashes.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ....core.config import settings
from ....mailer import get_mailer

router = APIRouter(prefix="/api/v1/dev", tags=["dev"])


class RecordingMailer:
    def __init__(self) -> None:
        self.links: dict[str, str] = {}

    async def send_verification(self, email: str, link: str) -> None:
        self.links[email.lower()] = link


def _err(code: str, message: str, status: int) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


@router.get("/last-verification-link")
async def last_verification_link(email: str = Query(...)) -> dict[str, str]:
    if settings.ENV == "prod":
        raise _err("dev_routes_disabled", "Not found.", 404)
    mailer = get_mailer()
    links = getattr(mailer, "links", None)
    if not isinstance(links, dict):
        raise _err("no_verification_link", "No verification link was recorded.", 404)
    link = links.get(email.lower())
    if link is None:
        raise _err("no_verification_link", "No verification link was recorded.", 404)
    return {"link": link}
