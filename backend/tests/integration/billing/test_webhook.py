import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.cloud.deps import set_cloud
from app.cloud.mock import InMemoryCloudControlPlane
from app.db.session import SessionLocal
from app.models.billing import StripeEvent, Subscription
from app.models.tenant import Tenant
from app.models.user import User

SECRET = "whsec_test_secret"


def _sign(body: bytes, ts: int | None = None) -> dict[str, str]:
    ts = ts if ts is not None else int(time.time())
    mac = hmac.new(SECRET.encode(), f"{ts}.".encode() + body, hashlib.sha256)
    return {"Stripe-Signature": f"t={ts},v1={mac.hexdigest()}"}


@pytest.fixture
def cloud() -> InMemoryCloudControlPlane:
    c = InMemoryCloudControlPlane()
    set_cloud(c)
    return c


async def _seed_incomplete_subscription() -> tuple[User, Subscription]:
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
            stripe_customer_id="cus_hook",
            stripe_subscription_id=None,
            status="incomplete",
        )
        db.add(sub)
        await db.commit()
        await db.refresh(user)
        await db.refresh(sub)
        return user, sub


def _checkout_event(user: User, event_id: str = "evt_hook_1") -> bytes:
    return json.dumps(
        {
            "id": event_id,
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "customer": "cus_hook",
                    "subscription": "sub_hook",
                    "metadata": {"hub_user_id": str(user.id)},
                }
            },
        }
    ).encode()


@pytest.mark.asyncio
async def test_webhook_rejects_a_missing_signature(client, cloud) -> None:
    r = await client.post("/api/v1/billing/webhook", content=b'{"id":"evt_x","type":"ping"}')
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_signature"


@pytest.mark.asyncio
async def test_webhook_rejects_a_tampered_body(client, cloud) -> None:
    body = b'{"id":"evt_x","type":"ping"}'
    headers = _sign(body)
    r = await client.post(
        "/api/v1/billing/webhook", content=b'{"id":"evt_y","type":"ping"}', headers=headers
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_signature"


@pytest.mark.asyncio
async def test_webhook_rejects_a_stale_signature(client, cloud) -> None:
    body = b'{"id":"evt_x","type":"ping"}'
    stale = int(time.time()) - 3600
    r = await client.post("/api/v1/billing/webhook", content=body, headers=_sign(body, stale))
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_signature"


@pytest.mark.asyncio
async def test_webhook_makes_no_state_change_when_the_signature_fails(client, cloud) -> None:
    user, _ = await _seed_incomplete_subscription()
    body = _checkout_event(user)
    r = await client.post(
        "/api/v1/billing/webhook", content=body, headers={"Stripe-Signature": "t=1,v1=deadbeef"}
    )
    assert r.status_code == 400
    assert cloud.create_calls == []
    async with SessionLocal() as db:
        assert (await db.execute(select(Tenant))).scalars().all() == []
        assert (await db.execute(select(StripeEvent))).scalars().all() == []


@pytest.mark.asyncio
async def test_valid_checkout_completed_creates_exactly_one_tenant(client, cloud) -> None:
    user, sub = await _seed_incomplete_subscription()
    body = _checkout_event(user)
    r = await client.post("/api/v1/billing/webhook", content=body, headers=_sign(body))
    assert r.status_code == 200
    assert r.json() == {"received": True, "duplicate": False, "action": "tenant_created"}
    assert len(cloud.create_calls) == 1
    async with SessionLocal() as db:
        stored = await db.scalar(select(Subscription).where(Subscription.id == sub.id))
        tenant = await db.scalar(select(Tenant).where(Tenant.subscription_id == sub.id))
    assert stored is not None and stored.status == "active"
    assert stored.stripe_subscription_id == "sub_hook"
    assert tenant is not None


@pytest.mark.asyncio
async def test_replaying_the_same_event_id_is_a_no_op(client, cloud) -> None:
    """Stripe retries. The second delivery must change nothing at all."""
    user, sub = await _seed_incomplete_subscription()
    body = _checkout_event(user)
    first = await client.post("/api/v1/billing/webhook", content=body, headers=_sign(body))
    assert first.json()["duplicate"] is False

    second = await client.post("/api/v1/billing/webhook", content=body, headers=_sign(body))
    assert second.status_code == 200
    assert second.json() == {"received": True, "duplicate": True, "action": "ignored"}

    assert len(cloud.create_calls) == 1
    assert len(cloud.tenants) == 1
    async with SessionLocal() as db:
        tenants = (await db.execute(select(Tenant))).scalars().all()
        events = (await db.execute(select(StripeEvent))).scalars().all()
    assert len(tenants) == 1
    assert len(events) == 1


@pytest.mark.asyncio
async def test_a_second_distinct_event_id_for_the_same_subscription_still_creates_one_tenant(
    client, cloud
) -> None:
    """Belt and braces: even if Stripe sends a NEW event id for the same checkout,
    tenant creation is idempotent at the service and contract layers."""
    user, _ = await _seed_incomplete_subscription()
    body_a = _checkout_event(user, event_id="evt_hook_a")
    body_b = _checkout_event(user, event_id="evt_hook_b")
    await client.post("/api/v1/billing/webhook", content=body_a, headers=_sign(body_a))
    await client.post("/api/v1/billing/webhook", content=body_b, headers=_sign(body_b))
    assert len(cloud.tenants) == 1
    async with SessionLocal() as db:
        assert len((await db.execute(select(Tenant))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_subscription_deleted_removes_the_tenant_and_is_replay_safe(client, cloud) -> None:
    user, sub = await _seed_incomplete_subscription()
    created = _checkout_event(user)
    await client.post("/api/v1/billing/webhook", content=created, headers=_sign(created))

    deleted = json.dumps(
        {
            "id": "evt_hook_del",
            "type": "customer.subscription.deleted",
            "data": {"object": {"id": "sub_hook", "customer": "cus_hook"}},
        }
    ).encode()
    r1 = await client.post("/api/v1/billing/webhook", content=deleted, headers=_sign(deleted))
    assert r1.json()["action"] == "tenant_deleted"
    r2 = await client.post("/api/v1/billing/webhook", content=deleted, headers=_sign(deleted))
    assert r2.json() == {"received": True, "duplicate": True, "action": "ignored"}

    assert len(cloud.delete_calls) == 1
    async with SessionLocal() as db:
        stored = await db.scalar(select(Subscription).where(Subscription.id == sub.id))
        assert stored is not None and stored.status == "canceled"
        assert (await db.execute(select(Tenant))).scalars().all() == []


@pytest.mark.asyncio
async def test_unhandled_event_type_is_recorded_but_changes_nothing(client, cloud) -> None:
    body = json.dumps(
        {"id": "evt_ignored", "type": "invoice.created", "data": {"object": {}}}
    ).encode()
    r = await client.post("/api/v1/billing/webhook", content=body, headers=_sign(body))
    assert r.status_code == 200
    assert r.json() == {"received": True, "duplicate": False, "action": "ignored"}
    assert cloud.create_calls == []
