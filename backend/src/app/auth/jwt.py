from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import jwt as pyjwt

from ..core.config import settings


def _now() -> int:
    return int(datetime.now(timezone.utc).timestamp())


class InvalidToken(Exception): ...


class InvalidTokenType(InvalidToken): ...


@dataclass(frozen=True)
class AccessClaims:
    sub: uuid.UUID
    email: str
    type: str
    iat: int
    exp: int
    jti: str


@dataclass(frozen=True)
class RefreshClaims:
    sub: uuid.UUID
    type: str
    iat: int
    exp: int
    jti: str


def issue_access(user_id: uuid.UUID, email: str) -> str:
    now = _now()
    payload = {
        "sub": str(user_id),
        "email": email,
        "type": "access",
        "iat": now,
        "exp": now + settings.ACCESS_TOKEN_TTL_SECONDS,
        "jti": secrets.token_urlsafe(16),
    }
    return pyjwt.encode(payload, settings.APP_JWT_SECRET, algorithm=settings.APP_JWT_ALGORITHM)


def issue_refresh(user_id: uuid.UUID, session_id: uuid.UUID) -> tuple[str, str]:
    """Returns (token, jti). Caller writes the jti into sessions.refresh_jti."""
    now = _now()
    jti = f"{session_id}:{secrets.token_urlsafe(16)}"
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "exp": now + settings.REFRESH_TOKEN_TTL_SECONDS,
        "jti": jti,
    }
    token = pyjwt.encode(
        payload, settings.APP_JWT_SECRET, algorithm=settings.APP_JWT_ALGORITHM
    )
    return token, jti


def _decode(token: str) -> dict[str, Any]:
    try:
        return pyjwt.decode(
            token, settings.APP_JWT_SECRET, algorithms=[settings.APP_JWT_ALGORITHM]
        )
    except pyjwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc


def verify_access(token: str) -> AccessClaims:
    payload = _decode(token)
    if payload.get("type") != "access":
        raise InvalidTokenType(f"expected access, got {payload.get('type')}")
    return AccessClaims(
        sub=uuid.UUID(payload["sub"]),
        email=payload["email"],
        type="access",
        iat=payload["iat"],
        exp=payload["exp"],
        jti=payload["jti"],
    )


def verify_refresh(token: str) -> RefreshClaims:
    payload = _decode(token)
    if payload.get("type") != "refresh":
        raise InvalidTokenType(f"expected refresh, got {payload.get('type')}")
    return RefreshClaims(
        sub=uuid.UUID(payload["sub"]),
        type="refresh",
        iat=payload["iat"],
        exp=payload["exp"],
        jti=payload["jti"],
    )
