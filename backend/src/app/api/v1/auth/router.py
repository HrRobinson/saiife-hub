from __future__ import annotations

import base64
import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from urllib.parse import urlencode

from authlib.common.security import generate_token
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ....auth import audit, password
from ....auth import jwt as ajwt
from ....auth.cookies import REFRESH_COOKIE, clear_session_cookies, set_session_cookies
from ....auth.deps import current_user
from ....auth.oauth_google import (
    GOOGLE_AUTH_URL,
    build_client,
    classify_match,
    exchange_code,
    fetch_userinfo,
)
from ....auth.passkeys import (
    challenge_expiry,
    detect_clone,
    make_authentication_options,
    make_registration_options,
    verify_authentication,
    verify_registration,
)
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
from ....models.user import (
    EmailVerification,
    OAuthAccount,
    Passkey,
    PasskeyChallenge,
    Session,
    User,
)

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


_state_serializer = URLSafeSerializer(settings.APP_JWT_SECRET, salt="oauth-state")


async def _google_exchange_and_userinfo(code: str, code_verifier: str) -> dict[str, Any]:
    client = build_client()
    token = await exchange_code(client, code, code_verifier)
    return await fetch_userinfo(client, token["access_token"])


@router.get("/google/start")
async def google_start() -> Response:
    code_verifier = generate_token(64)
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    state = secrets.token_urlsafe(24)
    cookie_value = _state_serializer.dumps({"state": state, "verifier": code_verifier})

    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "online",
        "prompt": "select_account",
    }
    response = Response(
        status_code=302, headers={"location": f"{GOOGLE_AUTH_URL}?{urlencode(params)}"}
    )
    response.set_cookie(
        "oauth_state",
        cookie_value,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=600,
        domain=settings.COOKIE_DOMAIN,
        path="/",
    )
    return response


@router.get("/google/callback")
async def google_callback(
    request: Request, code: str, state: str, db: AsyncSession = Depends(get_db)
) -> Response:
    raw_state_cookie = request.cookies.get("oauth_state")
    if not raw_state_cookie:
        raise _err("oauth_state_mismatch", "OAuth state missing or expired.", 400)
    try:
        state_data = _state_serializer.loads(raw_state_cookie)
    except BadSignature:
        raise _err("oauth_state_mismatch", "OAuth state signature invalid.", 400) from None
    if state_data.get("state") != state:
        raise _err("oauth_state_mismatch", "OAuth state mismatch.", 400)

    userinfo = await _google_exchange_and_userinfo(code, state_data["verifier"])
    google_sub = userinfo["sub"]
    google_email = str(userinfo["email"]).lower()
    google_email_verified = bool(userinfo.get("email_verified"))

    existing_oauth = await db.scalar(
        select(OAuthAccount).where(
            OAuthAccount.provider == "google", OAuthAccount.provider_sub == google_sub
        )
    )
    existing_user = await db.scalar(select(User).where(User.email == google_email))
    decision = classify_match(
        google_sub=google_sub,
        google_email=google_email,
        google_email_verified=google_email_verified,
        existing_oauth=existing_oauth,
        existing_user_by_email=existing_user,
    )

    if decision.action == "reject_google_unverified":
        raise _err("oauth_email_unverified", "Your Google account email is not verified.", 400)
    if decision.action == "reject_unverified_conflict":
        raise _err(
            "oauth_email_unverified_conflict",
            "An unverified account already uses this email — finish email verification first.",
            409,
        )

    if decision.action == "create_new":
        user = User(
            id=uuid.uuid4(),
            email=google_email,
            password_hash=None,
            email_verified_at=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.flush()
        db.add(
            OAuthAccount(
                id=uuid.uuid4(), user_id=user.id, provider="google",
                provider_sub=google_sub, email=google_email,
            )
        )
        await audit.log_event(
            db, user_id=user.id, event_type="signup", request=request, metadata={"via": "google"}
        )
    elif decision.action == "link_and_log_in":
        assert existing_user is not None  # classify_match guarantees this
        user = existing_user
        db.add(
            OAuthAccount(
                id=uuid.uuid4(), user_id=user.id, provider="google",
                provider_sub=google_sub, email=google_email,
            )
        )
        await audit.log_event(db, user_id=user.id, event_type="google_linked", request=request)
    else:  # log_in_existing
        assert decision.user_id is not None  # classify_match guarantees this
        found = await db.scalar(select(User).where(User.id == decision.user_id))
        assert found is not None  # OAuthAccount.user_id FK guarantees the row exists
        user = found

    response = Response(
        status_code=303, headers={"location": f"{settings.APP_URL}/oauth-callback"}
    )
    response.delete_cookie("oauth_state", domain=settings.COOKIE_DOMAIN, path="/")
    await _start_session(db, user, request, response)
    await audit.log_event(db, user_id=user.id, event_type="login_google", request=request)
    await db.commit()
    return response


@router.post("/passkey/register/start")
async def passkey_register_start(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    existing = (
        await db.execute(select(Passkey.credential_id).where(Passkey.user_id == user.id))
    ).scalars().all()
    challenge_bytes, options_json = make_registration_options(
        user_id=user.id, user_email=user.email, excluded_credential_ids=list(existing)
    )
    ch = PasskeyChallenge(
        id=uuid.uuid4(),
        user_id=user.id,
        challenge=challenge_bytes,
        type="registration",
        expires_at=challenge_expiry(),
    )
    db.add(ch)
    await db.commit()
    return {"challenge_id": str(ch.id), "options": json.loads(options_json)}


@router.post("/passkey/register/finish", status_code=201)
async def passkey_register_finish(
    request: Request, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    body = await request.json()
    ch = await db.scalar(
        select(PasskeyChallenge).where(
            PasskeyChallenge.id == uuid.UUID(body["challenge_id"]),
            PasskeyChallenge.user_id == user.id,
            PasskeyChallenge.type == "registration",
        )
    )
    if ch is None or ch.expires_at < datetime.now(timezone.utc):
        raise _err("passkey_challenge_invalid", "Passkey challenge expired — try again.", 400)
    verification = verify_registration(
        challenge=ch.challenge, response_json=json.dumps(body["response"])
    )
    pk = Passkey(
        id=uuid.uuid4(),
        user_id=user.id,
        credential_id=verification["credential_id"],
        public_key=verification["credential_public_key"],
        sign_count=verification["sign_count"],
        transports=body.get("transports"),
        name=body.get("name") or "Unnamed passkey",
    )
    db.add(pk)
    await db.delete(ch)
    await audit.log_event(
        db, user_id=user.id, event_type="passkey_added", request=request,
        metadata={"name": pk.name},
    )
    await db.commit()
    return {"id": str(pk.id), "name": pk.name, "created_at": pk.created_at.isoformat()}


@router.post("/passkey/login/start")
@limiter.limit("10/minute")
async def passkey_login_start(
    request: Request, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    # Discoverable-credentials flow — allow any registered credential.
    challenge_bytes, options_json = make_authentication_options(allow_credential_ids=[])
    ch = PasskeyChallenge(
        id=uuid.uuid4(),
        user_id=None,
        challenge=challenge_bytes,
        type="authentication",
        expires_at=challenge_expiry(),
    )
    db.add(ch)
    await db.commit()
    return {"challenge_id": str(ch.id), "options": json.loads(options_json)}


@router.post("/passkey/login/finish")
@limiter.limit("10/minute")
async def passkey_login_finish(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    body = await request.json()
    ch = await db.scalar(
        select(PasskeyChallenge).where(
            PasskeyChallenge.id == uuid.UUID(body["challenge_id"]),
            PasskeyChallenge.type == "authentication",
        )
    )
    if ch is None or ch.expires_at < datetime.now(timezone.utc):
        raise _err("passkey_challenge_invalid", "Passkey challenge expired — try again.", 400)
    raw_id = base64.urlsafe_b64decode(body["response"]["rawId"] + "==")
    pk = await db.scalar(select(Passkey).where(Passkey.credential_id == raw_id))
    if pk is None:
        raise _err("passkey_unknown", "This passkey is not registered.", 401)
    verification = verify_authentication(
        challenge=ch.challenge,
        response_json=json.dumps(body["response"]),
        public_key=pk.public_key,
        stored_sign_count=pk.sign_count,
    )
    if detect_clone(stored=pk.sign_count, new=verification["new_sign_count"]):
        await db.delete(pk)
        await audit.log_event(
            db, user_id=pk.user_id, event_type="passkey_clone_detected", request=request,
            metadata={"name": pk.name},
        )
        await db.commit()
        raise _err(
            "passkey_clone_detected",
            "This passkey was cloned and has been revoked. Register a new one.",
            401,
        )
    pk.sign_count = verification["new_sign_count"]
    pk.last_used_at = datetime.now(timezone.utc)
    await db.delete(ch)
    user = await db.scalar(select(User).where(User.id == pk.user_id))
    assert user is not None  # pk.user_id FK guarantees the row exists
    await _start_session(db, user, request, response)
    await audit.log_event(db, user_id=user.id, event_type="login_passkey", request=request)
    await db.commit()
    return _user_out(user).model_dump(mode="json")


@router.get("/passkeys")
async def list_passkeys(
    user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(Passkey).where(Passkey.user_id == user.id).order_by(Passkey.created_at)
        )
    ).scalars().all()
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "created_at": p.created_at.isoformat(),
            "last_used_at": p.last_used_at.isoformat() if p.last_used_at else None,
        }
        for p in rows
    ]


@router.patch("/passkeys/{passkey_id}")
async def rename_passkey(
    passkey_id: uuid.UUID,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    body = await request.json()
    pk = await db.scalar(
        select(Passkey).where(Passkey.id == passkey_id, Passkey.user_id == user.id)
    )
    if pk is None:
        raise _err("passkey_not_found", "Passkey not found.", 404)
    pk.name = body.get("name") or pk.name
    await db.commit()
    return {"id": str(pk.id), "name": pk.name}


@router.delete("/passkeys/{passkey_id}", status_code=204)
async def delete_passkey(
    passkey_id: uuid.UUID,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    pk = await db.scalar(
        select(Passkey).where(Passkey.id == passkey_id, Passkey.user_id == user.id)
    )
    if pk is None:
        raise _err("passkey_not_found", "Passkey not found.", 404)
    # Log BEFORE delete so pk.name is still readable.
    await audit.log_event(
        db, user_id=user.id, event_type="passkey_removed", request=request,
        metadata={"name": pk.name},
    )
    await db.delete(pk)
    await db.commit()
