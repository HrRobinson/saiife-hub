import uuid

import pytest
from sqlalchemy import select

from app.cloud.deps import set_cloud
from app.cloud.mock import InMemoryCloudControlPlane
from app.db.session import SessionLocal
from app.models.billing import Subscription
from app.models.tenant import Tenant
from app.tenants.tokens import parse_account_token, verify_account_secret

PEPPER = "test-pepper"


@pytest.fixture
def cloud() -> InMemoryCloudControlPlane:
    c = InMemoryCloudControlPlane()
    set_cloud(c)
    return c


async def _active_subscription(user_id: uuid.UUID) -> Subscription:
    async with SessionLocal() as db:
        sub = Subscription(
            id=uuid.uuid4(),
            user_id=user_id,
            stripe_customer_id=f"cus_{uuid.uuid4().hex[:8]}",
            stripe_subscription_id=f"sub_{uuid.uuid4().hex[:8]}",
            status="active",
        )
        db.add(sub)
        await db.commit()
        await db.refresh(sub)
        return sub


@pytest.mark.asyncio
async def test_issue_requires_authentication(client, cloud) -> None:
    r = await client.post(
        "/api/v1/tenants/account-token",
        cookies={"csrf_token": "x"},
        headers={"X-CSRF-Token": "x"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_issue_requires_an_active_subscription(client, signed_in_user, cloud) -> None:
    r = await client.post(
        "/api/v1/tenants/account-token",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    assert r.status_code == 402
    assert r.json()["error"]["code"] == "subscription_required"
    assert cloud.create_calls == []


@pytest.mark.asyncio
async def test_issue_returns_the_plaintext_token_once(client, signed_in_user, cloud) -> None:
    sub = await _active_subscription(signed_in_user["user"].id)
    r = await client.post(
        "/api/v1/tenants/account-token",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["token"].startswith("sfc_")
    assert body["cloud_tenant_id"].startswith("t_")

    parsed = parse_account_token(body["token"])
    assert parsed is not None
    async with SessionLocal() as db:
        tenant = await db.scalar(select(Tenant).where(Tenant.subscription_id == sub.id))
    assert tenant is not None
    assert verify_account_secret(parsed.secret, PEPPER, tenant.account_token_hash) is True


@pytest.mark.asyncio
async def test_the_token_is_never_returned_again(client, signed_in_user, cloud) -> None:
    await _active_subscription(signed_in_user["user"].id)
    issued = await client.post(
        "/api/v1/tenants/account-token",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    token = issued.json()["token"]

    me = await client.get("/api/v1/tenants/me", cookies=signed_in_user["cookies"])
    assert me.status_code == 200
    assert token not in me.text
    assert "token" not in me.json()
    assert me.json()["account_token_issued_at"] is not None


@pytest.mark.asyncio
async def test_issuing_again_rotates_the_token(client, signed_in_user, cloud) -> None:
    sub = await _active_subscription(signed_in_user["user"].id)
    first = (
        await client.post(
            "/api/v1/tenants/account-token",
            cookies=signed_in_user["cookies"],
            headers={"X-CSRF-Token": signed_in_user["csrf"]},
        )
    ).json()
    second = (
        await client.post(
            "/api/v1/tenants/account-token",
            cookies=signed_in_user["cookies"],
            headers={"X-CSRF-Token": signed_in_user["csrf"]},
        )
    ).json()

    assert first["token"] != second["token"]
    assert first["cloud_tenant_id"] == second["cloud_tenant_id"]
    assert len(cloud.tenants) == 1

    old = parse_account_token(first["token"])
    assert old is not None
    async with SessionLocal() as db:
        tenant = await db.scalar(select(Tenant).where(Tenant.subscription_id == sub.id))
    assert tenant is not None
    assert verify_account_secret(old.secret, PEPPER, tenant.account_token_hash) is False


@pytest.mark.asyncio
async def test_tenants_me_returns_404_before_a_tenant_exists(client, signed_in_user, cloud) -> None:
    r = await client.get("/api/v1/tenants/me", cookies=signed_in_user["cookies"])
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "no_tenant"
