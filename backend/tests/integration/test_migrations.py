"""Migrations must build the same schema the ORM expects — offline, on sqlite."""

import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

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
    inspector = inspect(create_engine(f"sqlite:///{db_file}"))
    assert EXPECTED_TABLES.issubset(set(inspector.get_table_names()))
