import uuid

import pytest
from sqlalchemy import select

from app.billing.gateway import MockStripeGateway, set_stripe_gateway
from app.db.session import SessionLocal
from app.models.billing import Subscription


@pytest.fixture(autouse=True)
def mock_gateway() -> MockStripeGateway:
    gw = MockStripeGateway()
    set_stripe_gateway(gw)
    return gw


@pytest.mark.asyncio
async def test_subscription_status_is_none_before_subscribing(client, signed_in_user) -> None:
    r = await client.get("/api/v1/billing/subscription", cookies=signed_in_user["cookies"])
    assert r.status_code == 200
    assert r.json() == {
        "status": "none",
        "current_period_end": None,
        "has_tenant": False,
        "account_token_issued_at": None,
    }


@pytest.mark.asyncio
async def test_checkout_session_requires_authentication(client) -> None:
    r = await client.post("/api/v1/billing/checkout-session", headers={"X-CSRF-Token": "x"},
                          cookies={"csrf_token": "x"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_checkout_session_returns_a_url_and_records_the_subscription(
    client, signed_in_user, mock_gateway
) -> None:
    r = await client.post(
        "/api/v1/billing/checkout-session",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    assert r.status_code == 200
    assert r.json()["url"] == "https://checkout.stripe.invalid/mock/cs_mock_1"
    assert mock_gateway.checkout_calls[0]["email"] == signed_in_user["user"].email

    async with SessionLocal() as db:
        sub = await db.scalar(
            select(Subscription).where(Subscription.user_id == signed_in_user["user"].id)
        )
    assert sub is not None
    assert sub.status == "incomplete"
    assert sub.stripe_customer_id == "cus_mock_1"


@pytest.mark.asyncio
async def test_checkout_session_reuses_an_existing_customer(
    client, signed_in_user, mock_gateway
) -> None:
    await client.post(
        "/api/v1/billing/checkout-session",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    await client.post(
        "/api/v1/billing/checkout-session",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(Subscription).where(Subscription.user_id == signed_in_user["user"].id)
            )
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].stripe_customer_id == "cus_mock_1"


@pytest.mark.asyncio
async def test_portal_session_requires_an_existing_customer(client, signed_in_user) -> None:
    r = await client.post(
        "/api/v1/billing/portal-session",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "no_subscription"


@pytest.mark.asyncio
async def test_portal_session_returns_a_url(client, signed_in_user, mock_gateway) -> None:
    async with SessionLocal() as db:
        db.add(
            Subscription(
                id=uuid.uuid4(),
                user_id=signed_in_user["user"].id,
                stripe_customer_id="cus_existing",
                stripe_subscription_id="sub_existing",
                status="active",
            )
        )
        await db.commit()
    r = await client.post(
        "/api/v1/billing/portal-session",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    assert r.status_code == 200
    assert r.json()["url"] == "https://billing.stripe.invalid/mock/cus_existing"
