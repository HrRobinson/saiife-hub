from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

# Routes exempt from the double-submit check: first-trust endpoints that have not
# issued the cookie yet, redirect endpoints Google calls, and the Stripe webhook
# (authenticated by HMAC signature, and Stripe cannot send our header).
_EXEMPT_PREFIXES = (
    "/api/v1/health",
    "/api/v1/auth/signup",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/auth/verify-email",
    "/api/v1/auth/resend-verification",
    "/api/v1/auth/google/start",
    "/api/v1/auth/google/callback",
    "/api/v1/auth/passkey/login/start",
    "/api/v1/auth/passkey/login/finish",
    "/api/v1/billing/webhook",
)

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _is_exempt(path: str) -> bool:
    return any(path.startswith(p) for p in _EXEMPT_PREFIXES)


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method in _SAFE_METHODS or _is_exempt(request.url.path):
            return await call_next(request)
        cookie = request.cookies.get("csrf_token")
        header = request.headers.get("x-csrf-token")
        if not cookie or not header:
            return JSONResponse(
                status_code=403,
                content={"error": {"code": "csrf_missing", "message": "Missing CSRF token."}},
            )
        if cookie != header:
            return JSONResponse(
                status_code=403,
                content={"error": {"code": "csrf_mismatch", "message": "CSRF token mismatch."}},
            )
        return await call_next(request)
