"""Migrations must build the same schema the ORM expects — offline, on sqlite."""

import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import MetaData, create_engine, insert, inspect

BACKEND = Path(__file__).parents[2]

EXPECTED_TABLES = {
    "users",
    "sessions",
    "oauth_accounts",
    "email_verifications",
    "passkeys",
    "passkey_challenges",
    "auth_events",
}


@pytest.mark.asyncio
async def test_alembic_upgrade_head_creates_auth_tables(tmp_path: Path) -> None:
    db_file = tmp_path / "migrated.db"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{db_file}",
        "PYTHONPATH": str(BACKEND / "src"),
    }
    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    engine = create_engine(f"sqlite:///{db_file}")
    inspector = inspect(engine)
    assert EXPECTED_TABLES.issubset(set(inspector.get_table_names()))

    # Regression guard: auth_events.id must be a sqlite rowid-alias PK so
    # that inserting a row without an explicit id (as the ORM does) works.
    # This only holds if the column compiles to exactly INTEGER on sqlite.
    metadata = MetaData()
    metadata.reflect(bind=engine, only=["auth_events"])
    auth_events = metadata.tables["auth_events"]
    with engine.begin() as conn:
        conn.execute(insert(auth_events).values(event_type="login"))
