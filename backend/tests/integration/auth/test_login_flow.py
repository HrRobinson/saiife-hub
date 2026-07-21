import pytest


async def _signup_and_verify(client, fake_mailer, email: str = "alice@example.com"):
    await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "correct-horse-battery-staple"},
    )
    link = fake_mailer.verifications[-1][1]
    token = link.split("token=")[1]
    return await client.post("/api/v1/auth/verify-email", json={"token": token})


@pytest.mark.asyncio
async def test_login_rejects_unverified(client, fake_mailer) -> None:
    await client.post(
        "/api/v1/auth/signup",
        json={"email": "alice@example.com", "password": "correct-horse-battery-staple"},
    )
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "correct-horse-battery-staple"},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "email_unverified"


@pytest.mark.asyncio
async def test_login_succeeds_for_verified_user(client, fake_mailer) -> None:
    rv = await _signup_and_verify(client, fake_mailer)
    assert rv.status_code == 200
    assert "s_access" in rv.cookies
    assert "s_refresh" in rv.cookies

    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "correct-horse-battery-staple"},
    )
    assert r.status_code == 200
    assert "s_access" in r.cookies
    assert "s_refresh" in r.cookies
    assert "csrf_token" in r.cookies


@pytest.mark.asyncio
async def test_login_rejects_wrong_password(client, fake_mailer) -> None:
    await _signup_and_verify(client, fake_mailer)
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "alice@example.com", "password": "not-the-right-password"},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_me_returns_the_signed_in_user(client, signed_in_user) -> None:
    r = await client.get("/api/v1/auth/me", cookies=signed_in_user["cookies"])
    assert r.status_code == 200
    assert r.json()["email"] == signed_in_user["user"].email
