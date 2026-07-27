"""Global test setup.

Environment is set BEFORE `app` is imported so `Settings` reads test values.
No network, no GCP, no Postgres: the database is a local sqlite file.
"""

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(_ROOT / "src"))

os.environ.setdefault("ENV", "test")
os.environ.setdefault("APP_VERSION", "test")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_ROOT / 'test-hub.db'}")
os.environ.setdefault("APP_JWT_SECRET", "test-only-jwt-secret-not-a-real-key")
os.environ.setdefault("ACCOUNT_TOKEN_PEPPER", "test-pepper")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_not_a_real_key")
os.environ.setdefault("STRIPE_PRICE_ID", "price_test_not_a_real_price")
os.environ.setdefault("COOKIE_DOMAIN", ".saiife.localhost")
os.environ.setdefault("COOKIE_SECURE", "true")

import pytest_asyncio


@pytest_asyncio.fixture(autouse=True)
async def db_ready() -> object:
    """Create a pristine schema before every test, fully offline (sqlite).

    Dropping and recreating rather than truncating keeps each test hermetic and
    avoids maintaining a TRUNCATE list as tables are added.
    """
    from app import models  # noqa: F401  -- registers every table on Base.metadata
    from app.db.base import Base
    from app.db.session import engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


import uuid as _uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def reset_rate_limiter() -> None:
    from app.core.rate_limit import limiter

    limiter.reset()


@dataclass
class FakeMailer:
    verifications: list[tuple[str, str]] = field(default_factory=list)

    async def send_verification(self, email: str, link: str) -> None:
        self.verifications.append((email, link))


@pytest.fixture
def fake_mailer() -> object:
    from app import mailer as mailer_mod

    fm = FakeMailer()
    mailer_mod.set_mailer(fm)
    yield fm
    mailer_mod.set_mailer(mailer_mod.ConsoleMailer())


@pytest_asyncio.fixture
async def client() -> object:
    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.saiife.localhost"
    ) as c:
        yield c


@pytest_asyncio.fixture
async def signed_in_user() -> dict[str, object]:
    """A verified user plus the cookies and CSRF token for signed-in requests."""
    from app.auth import jwt as ajwt
    from app.auth.cookies import ACCESS_COOKIE, CSRF_COOKIE, REFRESH_COOKIE
    from app.db.session import SessionLocal
    from app.models.user import User

    async with SessionLocal() as db:
        user = User(
            id=_uuid.uuid4(),
            email=f"u-{_uuid.uuid4().hex[:8]}@example.com",
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    access = ajwt.issue_access(user.id, user.email)
    refresh, _ = ajwt.issue_refresh(user.id, _uuid.uuid4())
    csrf = "csrf-test-token"
    return {
        "user": user,
        "cookies": {ACCESS_COOKIE: access, REFRESH_COOKIE: refresh, CSRF_COOKIE: csrf},
        "csrf": csrf,
    }
