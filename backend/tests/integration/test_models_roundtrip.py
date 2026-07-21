import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.user import AuthEvent, User


@pytest.mark.asyncio
async def test_user_roundtrips_and_auth_event_links(db_ready: None) -> None:
    uid = uuid.uuid4()
    async with SessionLocal() as db:
        db.add(User(id=uid, email="alice@example.com", email_verified_at=datetime.now(UTC)))
        await db.flush()
        db.add(AuthEvent(user_id=uid, event_type="signup", metadata_={"via": "password"}))
        await db.commit()

    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.id == uid))
        assert user is not None
        assert user.email == "alice@example.com"
        event = await db.scalar(select(AuthEvent).where(AuthEvent.user_id == uid))
        assert event is not None
        assert event.event_type == "signup"
        assert event.metadata_ == {"via": "password"}
