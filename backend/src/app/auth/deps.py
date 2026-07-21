from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_db
from ..models.user import User
from . import jwt as ajwt
from .cookies import ACCESS_COOKIE


async def current_user(
    s_access: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    if not s_access:
        raise HTTPException(401, detail={"code": "no_session", "message": "Not authenticated"})
    try:
        claims = ajwt.verify_access(s_access)
    except ajwt.InvalidToken:
        raise HTTPException(
            401, detail={"code": "token_expired", "message": "Session expired"}
        ) from None
    user = await db.scalar(select(User).where(User.id == claims.sub))
    if not user:
        raise HTTPException(
            401, detail={"code": "token_revoked", "message": "Account no longer exists"}
        )
    return user


async def verified_user(user: User = Depends(current_user)) -> User:
    if user.email_verified_at is None:
        raise HTTPException(403, detail={"code": "email_unverified", "message": "Verify your email"})
    return user
