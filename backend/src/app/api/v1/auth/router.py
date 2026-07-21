from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ....auth import audit, password
from ....auth import jwt as ajwt
from ....auth.cookies import REFRESH_COOKIE, clear_session_cookies, set_session_cookies
from ....auth.deps import current_user
from ....auth.schemas import (
    LoginRequest,
    ResendVerificationRequest,
    SignupRequest,
    UserOut,
    VerifyEmailRequest,
)
from ....core.config import settings
from ....core.rate_limit import limiter
from ....db.session import get_db
from ....mailer import get_mailer
from ....models.user import EmailVerification, Session, User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _err(code: str, message: str, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _user_out(u: User) -> UserOut:
    return UserOut(id=u.id, email=u.email, email_verified=u.email_verified_at is not None)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _as_aware_utc(dt: datetime) -> datetime:
    """SQLite (via aiosqlite) round-trips DateTime(timezone=True) columns as
    naive datetimes — it has no native tz-aware storage. Postgres preserves
    tzinfo natively, so this is a no-op there. Treat naive values as UTC so
    comparisons against datetime.now(timezone.utc) never raise."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


async def _start_session(
    db: AsyncSession, user: User, request: Request, response: Response
) -> Session:
    session = Session(
        id=uuid.uuid4(),
        user_id=user.id,
        refresh_jti="",  # filled below
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    db.add(session)
    await db.flush()

    access = ajwt.issue_access(user.id, user.email)
    refresh, jti = ajwt.issue_refresh(user.id, session.id)
    session.refresh_jti = jti
    csrf = secrets.token_urlsafe(32)
    set_session_cookies(response, access=access, refresh=refresh, csrf=csrf)
    return session


@router.post("/signup", status_code=201, response_model=UserOut)
@limiter.limit("5/hour")
async def signup(
    request: Request, body: SignupRequest, db: AsyncSession = Depends(get_db)
) -> UserOut:
    user = User(
        id=uuid.uuid4(),
        email=body.email.lower(),
        password_hash=password.hash_password(body.password),
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise _err(
            "email_taken", "An account with this email already exists.", status=409
        ) from None

    raw = secrets.token_urlsafe(32)
    db.add(
        EmailVerification(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=_hash_token(raw),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
    )
    await audit.log_event(db, user_id=user.id, event_type="signup", request=request)
    await db.commit()

    await get_mailer().send_verification(
        user.email, f"{settings.APP_URL}/verify-email?token={raw}"
    )
    return _user_out(user)


@router.post("/verify-email", response_model=UserOut)
async def verify_email(
    body: VerifyEmailRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    th = _hash_token(body.token)
    ev = await db.scalar(select(EmailVerification).where(EmailVerification.token_hash == th))
    if (
        ev is None
        or ev.used_at is not None
        or _as_aware_utc(ev.expires_at) < datetime.now(timezone.utc)
    ):
        raise _err(
            "verify_token_invalid", "This verification link is invalid or has expired.", 400
        )
    ev.used_at = datetime.now(timezone.utc)
    user = await db.scalar(select(User).where(User.id == ev.user_id))
    if user is None:
        raise _err("verify_token_invalid", "Account not found.", 400)
    user.email_verified_at = datetime.now(timezone.utc)
    await _start_session(db, user, request, response)
    await audit.log_event(db, user_id=user.id, event_type="email_verified", request=request)
    await db.commit()
    return _user_out(user)


@router.post("/resend-verification", status_code=200)
@limiter.limit("1/minute")
async def resend_verification(
    request: Request, body: ResendVerificationRequest, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    # Constant 200 regardless of user existence — no enumeration oracle.
    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    if user and user.email_verified_at is None:
        raw = secrets.token_urlsafe(32)
        db.add(
            EmailVerification(
                id=uuid.uuid4(),
                user_id=user.id,
                token_hash=_hash_token(raw),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            )
        )
        await db.commit()
        await get_mailer().send_verification(
            user.email, f"{settings.APP_URL}/verify-email?token={raw}"
        )
    return {"ok": True}


@router.post("/login", response_model=UserOut)
@limiter.limit("10/minute")
async def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    user = await db.scalar(select(User).where(User.email == body.email.lower()))
    # Always pay the argon2id cost, even when there's no real hash to check
    # against (unknown email, no local password) — otherwise the wrong-branch
    # short-circuit makes unknown-account requests return ~26x faster than
    # known-account ones, a trivial timing oracle for enumerating registered
    # emails despite the response bodies being byte-identical.
    stored_hash = (
        user.password_hash
        if user is not None and user.password_hash is not None
        else password.DUMMY_PASSWORD_HASH
    )
    password_ok = password.verify_password(stored_hash, body.password)
    if user is None or user.password_hash is None or not password_ok:
        raise _err("invalid_credentials", "Email or password is incorrect.", 401)
    if user.email_verified_at is None:
        raise _err("email_unverified", "Verify your email before signing in.", 403)
    if password.needs_rehash(user.password_hash):
        user.password_hash = password.hash_password(body.password)
    await _start_session(db, user, request, response)
    await audit.log_event(db, user_id=user.id, event_type="login_password", request=request)
    await db.commit()
    return _user_out(user)


@router.post("/refresh", response_model=UserOut)
async def refresh(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> UserOut:
    from sqlalchemy import update

    cookie = request.cookies.get(REFRESH_COOKIE)
    if not cookie:
        raise _err("no_refresh", "No refresh token.", 401)
    try:
        claims = ajwt.verify_refresh(cookie)
    except ajwt.InvalidToken:
        raise _err("token_expired", "Refresh token expired.", 401) from None

    session = await db.scalar(select(Session).where(Session.refresh_jti == claims.jti))
    if session is None or session.revoked_at is not None or session.rotated_to is not None:
        # Replay detection — revoke EVERY live session for this user. Only log
        # the lockdown event if this call actually revoked a still-live
        # session: once lockdown has already run, later replays of any dead
        # token in the chain hit this same branch and must not re-log.
        from sqlalchemy.engine import CursorResult

        result = cast(
            "CursorResult[Any]",
            await db.execute(
                update(Session)
                .where(Session.user_id == claims.sub, Session.revoked_at.is_(None))
                .values(revoked_at=datetime.now(timezone.utc))
            ),
        )
        if result.rowcount > 0:
            await audit.log_event(
                db, user_id=claims.sub, event_type="refresh_replay_lockdown", request=request
            )
        await db.commit()
        clear_session_cookies(response)
        raise _err("token_revoked", "Session revoked.", 401)

    user = await db.scalar(select(User).where(User.id == claims.sub))
    if user is None:
        raise _err("token_revoked", "Account not found.", 401)

    new_session = Session(
        id=uuid.uuid4(),
        user_id=user.id,
        refresh_jti="",
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )
    db.add(new_session)
    await db.flush()
    new_refresh, new_jti = ajwt.issue_refresh(user.id, new_session.id)
    new_session.refresh_jti = new_jti
    session.rotated_to = new_session.id
    session.revoked_at = datetime.now(timezone.utc)

    access = ajwt.issue_access(user.id, user.email)
    csrf = secrets.token_urlsafe(32)
    set_session_cookies(response, access=access, refresh=new_refresh, csrf=csrf)
    await audit.log_event(db, user_id=user.id, event_type="refresh", request=request)
    await db.commit()
    return _user_out(user)


@router.post("/logout", status_code=204)
async def logout(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> None:
    from sqlalchemy import update

    cookie = request.cookies.get(REFRESH_COOKIE)
    if cookie:
        try:
            claims = ajwt.verify_refresh(cookie)
        except ajwt.InvalidToken:
            pass
        else:
            await db.execute(
                update(Session)
                .where(Session.refresh_jti == claims.jti)
                .values(revoked_at=datetime.now(timezone.utc))
            )
            await audit.log_event(
                db, user_id=claims.sub, event_type="logout", request=request
            )
            await db.commit()
    clear_session_cookies(response)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)) -> UserOut:
    return _user_out(user)
