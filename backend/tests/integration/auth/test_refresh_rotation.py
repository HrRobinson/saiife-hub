import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.user import AuthEvent


async def _signup_and_verify(client, fake_mailer, email: str = "alice@example.com"):
    await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "correct-horse-battery-staple"},
    )
    link = fake_mailer.verifications[-1][1]
    token = link.split("token=")[1]
    return await client.post("/api/v1/auth/verify-email", json={"token": token})


@pytest.mark.asyncio
async def test_refresh_rotates_token_and_locks_down_on_replay(client, fake_mailer) -> None:
    rv = await _signup_and_verify(client, fake_mailer)
    old_refresh = rv.cookies["s_refresh"]

    r1 = await client.post("/api/v1/auth/refresh", cookies={"s_refresh": old_refresh})
    assert r1.status_code == 200
    new_refresh = r1.cookies["s_refresh"]
    assert new_refresh != old_refresh

    # Replaying the OLD token must fail AND revoke every session.
    r2 = await client.post("/api/v1/auth/refresh", cookies={"s_refresh": old_refresh})
    assert r2.status_code == 401
    assert r2.json()["error"]["code"] == "token_revoked"

    # The rotated NEW token is now dead too — that is the lockdown.
    r3 = await client.post("/api/v1/auth/refresh", cookies={"s_refresh": new_refresh})
    assert r3.status_code == 401

    async with SessionLocal() as db:
        events = (
            await db.execute(
                select(AuthEvent.event_type).where(
                    AuthEvent.event_type == "refresh_replay_lockdown"
                )
            )
        ).scalars().all()
    assert len(events) == 1


@pytest.mark.asyncio
async def test_refresh_without_cookie_is_401(client) -> None:
    r = await client.post("/api/v1/auth/refresh")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "no_refresh"
