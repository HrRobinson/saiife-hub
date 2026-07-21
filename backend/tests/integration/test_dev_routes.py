import pytest

from app import mailer as mailer_mod
from app.api.v1.dev.router import RecordingMailer


@pytest.fixture
def recording() -> RecordingMailer:
    rec = RecordingMailer()
    mailer_mod.set_mailer(rec)
    yield rec
    mailer_mod.set_mailer(mailer_mod.ConsoleMailer())


@pytest.mark.asyncio
async def test_returns_the_last_verification_link_for_an_email(client, recording) -> None:
    await client.post(
        "/api/v1/auth/signup",
        json={"email": "dev@example.com", "password": "correct-horse-battery-staple"},
    )
    r = await client.get("/api/v1/dev/last-verification-link", params={"email": "dev@example.com"})
    assert r.status_code == 200
    assert "verify-email?token=" in r.json()["link"]


@pytest.mark.asyncio
async def test_returns_404_for_an_unknown_email(client, recording) -> None:
    r = await client.get("/api/v1/dev/last-verification-link", params={"email": "nope@example.com"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "no_verification_link"


@pytest.mark.asyncio
async def test_dev_routes_are_disabled_in_prod(
    client, recording, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "ENV", "prod")
    r = await client.get("/api/v1/dev/last-verification-link", params={"email": "dev@example.com"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "dev_routes_disabled"
