import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.models.billing import StripeEvent, Subscription
from app.models.install import Install
from app.models.tenant import Tenant
from app.models.user import User


async def _user() -> User:
    async with SessionLocal() as db:
        u = User(
            id=uuid.uuid4(),
            email=f"u-{uuid.uuid4().hex[:8]}@example.com",
            email_verified_at=datetime.now(UTC),
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
        return u


@pytest.mark.asyncio
async def test_subscription_tenant_and_install_roundtrip() -> None:
    user = await _user()
    sub_id, tenant_id, install_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with SessionLocal() as db:
        db.add(
            Subscription(
                id=sub_id,
                user_id=user.id,
                stripe_customer_id="cus_1",
                stripe_subscription_id="sub_1",
                status="active",
                current_period_end=datetime.now(UTC),
            )
        )
        await db.flush()
        db.add(
            Tenant(
                id=tenant_id,
                user_id=user.id,
                subscription_id=sub_id,
                cloud_tenant_id="t_abc",
                tenant_lookup_id="0123456789abcdef01",
                account_token_hash="scrypt$16384$8$1$c2FsdA==$aGFzaA==",
                account_token_hash_algo="scrypt",
                account_token_issued_at=None,
            )
        )
        db.add(Install(id=install_id, user_id=user.id, name="Work laptop"))
        await db.commit()

    async with SessionLocal() as db:
        tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
        assert tenant is not None
        assert tenant.cloud_tenant_id == "t_abc"
        assert tenant.account_token_issued_at is None
        install = await db.scalar(select(Install).where(Install.id == install_id))
        assert install is not None
        assert install.name == "Work laptop"


@pytest.mark.asyncio
async def test_stripe_event_id_is_the_primary_key_so_replays_collide() -> None:
    async with SessionLocal() as db:
        db.add(StripeEvent(event_id="evt_1", event_type="checkout.session.completed"))
        await db.commit()

    with pytest.raises(IntegrityError):
        async with SessionLocal() as db:
            db.add(StripeEvent(event_id="evt_1", event_type="checkout.session.completed"))
            await db.commit()


@pytest.mark.asyncio
async def test_one_subscription_per_user() -> None:
    user = await _user()
    async with SessionLocal() as db:
        db.add(
            Subscription(
                id=uuid.uuid4(), user_id=user.id,
                stripe_customer_id="cus_a", stripe_subscription_id="sub_a", status="active",
            )
        )
        await db.commit()
    with pytest.raises(IntegrityError):
        async with SessionLocal() as db:
            db.add(
                Subscription(
                    id=uuid.uuid4(), user_id=user.id,
                    stripe_customer_id="cus_b", stripe_subscription_id="sub_b", status="active",
                )
            )
            await db.commit()
