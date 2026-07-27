import pytest

from app import mailer as mailer_mod


class RecordingMailer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_verification(self, email: str, link: str) -> None:
        self.sent.append((email, link))


def test_default_mailer_is_console() -> None:
    mailer_mod.set_mailer(mailer_mod.ConsoleMailer())
    assert isinstance(mailer_mod.get_mailer(), mailer_mod.ConsoleMailer)


@pytest.mark.asyncio
async def test_set_mailer_replaces_the_active_mailer() -> None:
    rec = RecordingMailer()
    mailer_mod.set_mailer(rec)
    await mailer_mod.get_mailer().send_verification("a@example.com", "https://x/verify?token=t")
    assert rec.sent == [("a@example.com", "https://x/verify?token=t")]
    mailer_mod.set_mailer(mailer_mod.ConsoleMailer())


def test_configure_default_stays_console_without_mailgun_credentials() -> None:
    """No key + no domain => never attempt a network call."""
    mailer_mod.configure_default_mailer()
    assert isinstance(mailer_mod.get_mailer(), mailer_mod.ConsoleMailer)
