from __future__ import annotations

from typing import Any

from fastapi import Response

from ..core.config import settings

ACCESS_COOKIE = "s_access"
REFRESH_COOKIE = "s_refresh"
CSRF_COOKIE = "csrf_token"


def _common() -> dict[str, Any]:
    return {
        "domain": settings.COOKIE_DOMAIN,
        "secure": settings.COOKIE_SECURE,
        "samesite": settings.COOKIE_SAMESITE,
        "path": "/",
    }


def set_session_cookies(resp: Response, *, access: str, refresh: str, csrf: str) -> None:
    resp.set_cookie(
        ACCESS_COOKIE, access, httponly=True,
        max_age=settings.ACCESS_TOKEN_TTL_SECONDS, **_common(),
    )
    resp.set_cookie(
        REFRESH_COOKIE, refresh, httponly=True,
        max_age=settings.REFRESH_TOKEN_TTL_SECONDS, **_common(),
    )
    # CSRF is readable from JS — the frontend echoes it back as X-CSRF-Token.
    resp.set_cookie(
        CSRF_COOKIE, csrf, httponly=False,
        max_age=settings.REFRESH_TOKEN_TTL_SECONDS, **_common(),
    )


def clear_session_cookies(resp: Response) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        resp.delete_cookie(name, domain=settings.COOKIE_DOMAIN, path="/")
