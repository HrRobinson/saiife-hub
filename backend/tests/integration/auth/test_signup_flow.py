import pytest


@pytest.mark.asyncio
async def test_signup_creates_unverified_user_and_emails_link(client, fake_mailer) -> None:
    r = await client.post(
        "/api/v1/auth/signup",
        json={"email": "alice@example.com", "password": "correct-horse-battery-staple"},
    )
    assert r.status_code == 201
    assert r.json()["email"] == "alice@example.com"
    assert r.json()["email_verified"] is False
    # No session cookies — the user must verify first.
    assert "s_access" not in r.cookies
    assert len(fake_mailer.verifications) == 1
    to, link = fake_mailer.verifications[0]
    assert to == "alice@example.com"
    assert "verify-email?token=" in link


@pytest.mark.asyncio
async def test_signup_rejects_duplicate_email(client, fake_mailer) -> None:
    payload = {"email": "alice@example.com", "password": "correct-horse-battery-staple"}
    assert (await client.post("/api/v1/auth/signup", json=payload)).status_code == 201
    r2 = await client.post("/api/v1/auth/signup", json=payload)
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "email_taken"


@pytest.mark.asyncio
async def test_signup_rejects_short_password(client, fake_mailer) -> None:
    r = await client.post(
        "/api/v1/auth/signup", json={"email": "x@example.com", "password": "short"}
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_resend_verification_is_not_an_enumeration_oracle(client, fake_mailer) -> None:
    known = await client.post(
        "/api/v1/auth/resend-verification", json={"email": "nobody@example.com"}
    )
    assert known.status_code == 200
    assert known.json() == {"ok": True}
    assert fake_mailer.verifications == []
