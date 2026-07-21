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
