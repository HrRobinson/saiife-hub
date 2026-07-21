from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_google_start_redirects_to_google(client) -> None:
    r = await client.get("/api/v1/auth/google/start", follow_redirects=False)
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith("https://accounts.google.com/o/oauth2/v2/auth")
    assert "code_challenge=" in loc
    assert "code_challenge_method=S256" in loc
    assert "oauth_state" in r.cookies


@pytest.mark.asyncio
async def test_google_callback_creates_user_on_first_login(client) -> None:
    r0 = await client.get("/api/v1/auth/google/start", follow_redirects=False)
    state = r0.headers["location"].split("state=")[1].split("&")[0]

    fake_userinfo = {"sub": "g-12345", "email": "newuser@example.com", "email_verified": True}
    with patch(
        "app.api.v1.auth.router._google_exchange_and_userinfo",
        new=AsyncMock(return_value=fake_userinfo),
    ):
        r = await client.get(
            "/api/v1/auth/google/callback",
            params={"code": "fakecode", "state": state},
            follow_redirects=False,
            cookies=r0.cookies,
        )
    assert r.status_code in (302, 303)
    assert "s_access" in r.cookies
    assert "s_refresh" in r.cookies


@pytest.mark.asyncio
async def test_google_callback_rejects_state_mismatch(client) -> None:
    r0 = await client.get("/api/v1/auth/google/start", follow_redirects=False)
    r = await client.get(
        "/api/v1/auth/google/callback",
        params={"code": "fakecode", "state": "wrong-state"},
        follow_redirects=False,
        cookies=r0.cookies,
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "oauth_state_mismatch"
