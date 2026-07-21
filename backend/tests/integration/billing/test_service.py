import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.billing.service import apply_stripe_event
from app.cloud.mock import InMemoryCloudControlPlane
from app.db.session import SessionLocal
from app.models.billing import Subscription
from app.models.tenant import Tenant
from app.models.user import User
from app.tenants.service import ensure_tenant, issue_account_token, remove_tenant
from app.tenants.tokens import parse_account_token, verify_account_secret

PEPPER = "test-pepper"


async def _user_and_subscription(status: str = "active") -> tuple[User, Subscription]:
    async with SessionLocal() as db:
        user = User(
            id=uuid.uuid4(),
            email=f"u-{uuid.uuid4().hex[:8]}@example.com",
            email_verified_at=datetime.now(UTC),
        )
        db.add(user)
        await db.flush()
        sub = Subscription(
            id=uuid.uuid4(),
            user_id=user.id,
            stripe_customer_id=f"cus_{uuid.uuid4().hex[:8]}",
            stripe_subscription_id=f"sub_{uuid.uuid4().hex[:8]}",
            status=status,
        )
        db.add(sub)
        await db.commit()
        await db.refresh(user)
        await db.refresh(sub)
        return user, sub


@pytest.mark.asyncio
async def test_ensure_tenant_creates_exactly_one_tenant() -> None:
    _, sub = await _user_and_subscription()
    cloud = InMemoryCloudControlPlane()
    async with SessionLocal() as db:
        sub = await db.merge(sub)
        tenant = await ensure_tenant(db, cloud, subscription=sub, pepper=PEPPER)
        await db.commit()
    assert tenant.cloud_tenant_id.startswith("t_")
    assert tenant.account_token_issued_at is None
    assert len(cloud.create_calls) == 1
    assert cloud.create_calls[0].external_ref == f"hub:{sub.stripe_subscription_id}"


@pytest.mark.asyncio
async def test_ensure_tenant_is_idempotent_and_does_not_call_cloud_twice() -> None:
    _, sub = await _user_and_subscription()
    cloud = InMemoryCloudControlPlane()
    async with SessionLocal() as db:
        sub = await db.merge(sub)
        first = await ensure_tenant(db, cloud, subscription=sub, pepper=PEPPER)
        await db.commit()
    async with SessionLocal() as db:
        sub = await db.merge(sub)
        second = await ensure_tenant(db, cloud, subscription=sub, pepper=PEPPER)
        await db.commit()
    assert first.cloud_tenant_id == second.cloud_tenant_id
    assert len(cloud.create_calls) == 1
    async with SessionLocal() as db:
        rows = (await db.execute(select(Tenant))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_issue_account_token_returns_a_verifiable_token_and_stores_only_the_hash() -> None:
    _, sub = await _user_and_subscription()
    cloud = InMemoryCloudControlPlane()
    async with SessionLocal() as db:
        sub = await db.merge(sub)
        await ensure_tenant(db, cloud, subscription=sub, pepper=PEPPER)
        await db.commit()
    async with SessionLocal() as db:
        sub = await db.merge(sub)
        issued = await issue_account_token(db, cloud, subscription=sub, pepper=PEPPER)
        await db.commit()

    parsed = parse_account_token(issued.token)
    assert parsed is not None
    async with SessionLocal() as db:
        tenant = await db.scalar(select(Tenant).where(Tenant.subscription_id == sub.id))
    assert tenant is not None
    assert tenant.tenant_lookup_id == parsed.tenant_lookup_id
    assert tenant.account_token_issued_at is not None
    assert verify_account_secret(parsed.secret, PEPPER, tenant.account_token_hash) is True
    # The plaintext is nowhere in the stored row.
    assert issued.token not in tenant.account_token_hash
    assert parsed.secret not in tenant.account_token_hash


@pytest.mark.asyncio
async def test_issuing_twice_rotates_and_invalidates_the_previous_token() -> None:
    _, sub = await _user_and_subscription()
    cloud = InMemoryCloudControlPlane()
    async with SessionLocal() as db:
        sub = await db.merge(sub)
        await ensure_tenant(db, cloud, subscription=sub, pepper=PEPPER)
        first = await issue_account_token(db, cloud, subscription=sub, pepper=PEPPER)
        await db.commit()
    async with SessionLocal() as db:
        sub = await db.merge(sub)
        second = await issue_account_token(db, cloud, subscription=sub, pepper=PEPPER)
        await db.commit()

    assert first.token != second.token
    assert first.cloud_tenant_id == second.cloud_tenant_id
    async with SessionLocal() as db:
        tenant = await db.scalar(select(Tenant).where(Tenant.subscription_id == sub.id))
    assert tenant is not None
    old = parse_account_token(first.token)
    new = parse_account_token(second.token)
    assert old is not None and new is not None
    assert verify_account_secret(old.secret, PEPPER, tenant.account_token_hash) is False
    assert verify_account_secret(new.secret, PEPPER, tenant.account_token_hash) is True


@pytest.mark.asyncio
async def test_remove_tenant_deletes_in_cloud_and_locally_and_is_idempotent() -> None:
    _, sub = await _user_and_subscription()
    cloud = InMemoryCloudControlPlane()
    async with SessionLocal() as db:
        sub = await db.merge(sub)
        tenant = await ensure_tenant(db, cloud, subscription=sub, pepper=PEPPER)
        await db.commit()
        cloud_tenant_id = tenant.cloud_tenant_id
    async with SessionLocal() as db:
        sub = await db.merge(sub)
        await remove_tenant(db, cloud, subscription=sub)
        await db.commit()
    async with SessionLocal() as db:
        sub = await db.merge(sub)
        await remove_tenant(db, cloud, subscription=sub)  # no raise
        await db.commit()

    assert cloud.delete_calls == [cloud_tenant_id]
    assert cloud.tenants == {}
    async with SessionLocal() as db:
        assert (await db.execute(select(Tenant))).scalars().all() == []


@pytest.mark.asyncio
async def test_checkout_completed_activates_the_subscription_and_creates_a_tenant() -> None:
    user, sub = await _user_and_subscription(status="incomplete")
    cloud = InMemoryCloudControlPlane()
    event = {
        "id": "evt_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": sub.stripe_customer_id,
                "subscription": sub.stripe_subscription_id,
                "metadata": {"hub_user_id": str(user.id)},
            }
        },
    }
    async with SessionLocal() as db:
        action = await apply_stripe_event(db, cloud, event=event, pepper=PEPPER)
        await db.commit()
    assert action == "tenant_created"
    async with SessionLocal() as db:
        stored = await db.scalar(select(Subscription).where(Subscription.id == sub.id))
        tenant = await db.scalar(select(Tenant).where(Tenant.subscription_id == sub.id))
    assert stored is not None and stored.status == "active"
    assert tenant is not None
    assert len(cloud.create_calls) == 1


@pytest.mark.asyncio
async def test_subscription_deleted_cancels_and_removes_the_tenant() -> None:
    user, sub = await _user_and_subscription()
    cloud = InMemoryCloudControlPlane()
    async with SessionLocal() as db:
        merged = await db.merge(sub)
        await ensure_tenant(db, cloud, subscription=merged, pepper=PEPPER)
        await db.commit()
    event = {
        "id": "evt_2",
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": sub.stripe_subscription_id, "customer": sub.stripe_customer_id}},
    }
    async with SessionLocal() as db:
        action = await apply_stripe_event(db, cloud, event=event, pepper=PEPPER)
        await db.commit()
    assert action == "tenant_deleted"
    async with SessionLocal() as db:
        stored = await db.scalar(select(Subscription).where(Subscription.id == sub.id))
        assert stored is not None and stored.status == "canceled"
        assert (await db.execute(select(Tenant))).scalars().all() == []


@pytest.mark.asyncio
async def test_unhandled_event_type_is_a_no_op() -> None:
    cloud = InMemoryCloudControlPlane()
    async with SessionLocal() as db:
        action = await apply_stripe_event(
            db, cloud, event={"id": "evt_3", "type": "invoice.created", "data": {"object": {}}},
            pepper=PEPPER,
        )
        await db.commit()
    assert action == "ignored"
    assert cloud.create_calls == []
