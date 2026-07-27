import hashlib
import hmac
import json
import re
import time
import uuid

import pytest
from sqlalchemy import select

from app.billing.gateway import MockStripeGateway, set_stripe_gateway
from app.db.session import SessionLocal
from app.models.billing import Subscription

WEBHOOK_SECRET = "whsec_test_secret"


def _sign(body: bytes) -> dict[str, str]:
    ts = int(time.time())
    mac = hmac.new(WEBHOOK_SECRET.encode(), f"{ts}.".encode() + body, hashlib.sha256)
    return {"Stripe-Signature": f"t={ts},v1={mac.hexdigest()}"}


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
    r2 = await client.post(
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

    # Gateway-level reuse: the second call must actually ask Stripe to reuse
    # the existing customer, not merely leave the DB row untouched.
    assert len(mock_gateway.checkout_calls) == 2
    assert mock_gateway.checkout_calls[0]["existing_customer_id"] is None
    assert mock_gateway.checkout_calls[1]["existing_customer_id"] == "cus_mock_1"
    assert r2.json()["url"] == "https://checkout.stripe.invalid/mock/cs_mock_2"


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


@pytest.mark.asyncio
async def test_second_checkout_since_process_start_needs_its_own_customer_id(
    client, signed_in_user, mock_gateway
) -> None:
    """Reproduces the stateful-counter bug that the e2e spec was hitting.

    `MockStripeGateway` is a module-level singleton whose `_counter` (see
    app/billing/gateway.py) increments for the lifetime of the process, not
    per test/run. So a hardcoded `cus_mock_1` in a fabricated webhook only
    ever matches the *first* checkout since the gateway was constructed.
    Here we simulate "a developer already clicked Subscribe once" by driving
    the gateway to n=1 for someone else first, then prove:

      1. a webhook using the stale, hardcoded "cus_mock_1" id does NOT
         resolve to this run's subscription (the exact failure mode
         described in the finding), and
      2. deriving the id from *this* run's own checkout-session response --
         the same technique the fixed e2e spec now uses -- does.
    """
    # Bump the shared counter to n=1 via an unrelated checkout, exactly like
    # "a developer clicked Subscribe manually first" against a long-lived
    # dev server.
    await mock_gateway.create_checkout_session(
        user_id="00000000-0000-0000-0000-000000000000",
        email="someone-else@example.com",
        price_id="price_test",
        success_url="https://x.invalid",
        cancel_url="https://x.invalid",
    )

    # This run's own checkout is therefore n=2.
    checkout = await client.post(
        "/api/v1/billing/checkout-session",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    assert checkout.status_code == 200
    checkout_url = checkout.json()["url"]
    assert checkout_url == "https://checkout.stripe.invalid/mock/cs_mock_2"

    # Same derivation the fixed spec performs: pull the mock session id back
    # out of the (client-observable) checkout URL and reuse its numeric
    # suffix, since MockStripeGateway mints session id and customer id from
    # the same counter value in one call.
    session_id_match = re.search(r"cs_mock_(\d+)", checkout_url)
    assert session_id_match is not None
    derived_customer_id = f"cus_mock_{session_id_match.group(1)}"
    assert derived_customer_id == "cus_mock_2"

    # 1. The old, hardcoded id: proves the bug. It resolves to nothing for
    #    this run, so the webhook cannot create a tenant.
    stale_body = json.dumps(
        {
            "id": f"evt_stale_{uuid.uuid4().hex[:8]}",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "customer": "cus_mock_1",
                    "subscription": f"sub_stale_{uuid.uuid4().hex[:8]}",
                    "metadata": {},
                }
            },
        }
    ).encode()
    stale_hook = await client.post(
        "/api/v1/billing/webhook", content=stale_body, headers=_sign(stale_body)
    )
    assert stale_hook.status_code == 200
    assert stale_hook.json()["action"] == "unknown_subscription"

    # 2. The derived id: proves the fix. It matches the Subscription row the
    #    checkout-session call just created for THIS run's customer id.
    async with SessionLocal() as db:
        sub = await db.scalar(
            select(Subscription).where(Subscription.user_id == signed_in_user["user"].id)
        )
    assert sub is not None
    assert sub.stripe_customer_id == derived_customer_id

    fresh_body = json.dumps(
        {
            "id": f"evt_fresh_{uuid.uuid4().hex[:8]}",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "customer": derived_customer_id,
                    "subscription": f"sub_fresh_{uuid.uuid4().hex[:8]}",
                    "metadata": {},
                }
            },
        }
    ).encode()
    fresh_hook = await client.post(
        "/api/v1/billing/webhook", content=fresh_body, headers=_sign(fresh_body)
    )
    assert fresh_hook.status_code == 200
    assert fresh_hook.json()["action"] == "tenant_created"
