import uuid

import pytest

from app.cloud.contracts import DeliveryRecord, IngressUrl
from app.cloud.deps import set_cloud
from app.cloud.http import HttpCloudControlPlane
from app.cloud.mock import InMemoryCloudControlPlane
from app.db.session import SessionLocal
from app.models.billing import Subscription
from app.models.tenant import Tenant


@pytest.fixture
def cloud() -> InMemoryCloudControlPlane:
    c = InMemoryCloudControlPlane()
    set_cloud(c)
    return c


async def _tenant_for(user_id: uuid.UUID, cloud_tenant_id: str = "t_test") -> Tenant:
    async with SessionLocal() as db:
        sub = Subscription(
            id=uuid.uuid4(),
            user_id=user_id,
            stripe_customer_id=f"cus_{uuid.uuid4().hex[:8]}",
            stripe_subscription_id=f"sub_{uuid.uuid4().hex[:8]}",
            status="active",
        )
        db.add(sub)
        await db.flush()
        tenant = Tenant(
            id=uuid.uuid4(),
            user_id=user_id,
            subscription_id=sub.id,
            cloud_tenant_id=cloud_tenant_id,
            tenant_lookup_id=uuid.uuid4().hex[:18],
            account_token_hash="scrypt$16384$8$1$c2FsdA==$aGFzaA==",
            account_token_hash_algo="scrypt",
        )
        db.add(tenant)
        await db.commit()
        await db.refresh(tenant)
        return tenant


@pytest.mark.asyncio
async def test_installs_start_empty(client, signed_in_user, cloud) -> None:
    r = await client.get("/api/v1/installs", cookies=signed_in_user["cookies"])
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_create_list_and_delete_an_install(client, signed_in_user, cloud) -> None:
    created = await client.post(
        "/api/v1/installs",
        json={"name": "Work laptop"},
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    assert created.status_code == 201
    install_id = created.json()["id"]
    assert created.json()["name"] == "Work laptop"

    listed = await client.get("/api/v1/installs", cookies=signed_in_user["cookies"])
    assert [i["name"] for i in listed.json()] == ["Work laptop"]

    deleted = await client.delete(
        f"/api/v1/installs/{install_id}",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    assert deleted.status_code == 204
    assert (await client.get("/api/v1/installs", cookies=signed_in_user["cookies"])).json() == []


@pytest.mark.asyncio
async def test_deleting_someone_elses_install_is_404(client, signed_in_user, cloud) -> None:
    r = await client.delete(
        f"/api/v1/installs/{uuid.uuid4()}",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "install_not_found"


@pytest.mark.asyncio
async def test_ingress_urls_require_a_tenant(client, signed_in_user, cloud) -> None:
    r = await client.get("/api/v1/installs/ingress-urls", cookies=signed_in_user["cookies"])
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "no_tenant"


@pytest.mark.asyncio
async def test_ingress_urls_proxy_the_cloud_control_plane(client, signed_in_user, cloud) -> None:
    await _tenant_for(signed_in_user["user"].id, "t_proxy")
    cloud.seed_ingress_url(
        "t_proxy",
        IngressUrl(
            id="ig_1", integration="stripe",
            url="https://wh.example.invalid/wh/ig_1", created_at="2026-07-21T10:00:00.000Z",
        ),
    )
    r = await client.get("/api/v1/installs/ingress-urls", cookies=signed_in_user["cookies"])
    assert r.status_code == 200
    assert r.json() == {
        "ingress_urls": [
            {
                "id": "ig_1",
                "integration": "stripe",
                "url": "https://wh.example.invalid/wh/ig_1",
                "created_at": "2026-07-21T10:00:00.000Z",
            }
        ]
    }


@pytest.mark.asyncio
async def test_deliveries_proxy_the_cloud_control_plane(client, signed_in_user, cloud) -> None:
    await _tenant_for(signed_in_user["user"].id, "t_deliver")
    cloud.seed_delivery(
        "t_deliver",
        DeliveryRecord(
            delivery_id="dl_1", ingress_id="ig_1", integration="stripe",
            received_at="2026-07-21T10:00:01.000Z", status="published",
        ),
    )
    r = await client.get(
        "/api/v1/installs/deliveries?limit=10", cookies=signed_in_user["cookies"]
    )
    assert r.status_code == 200
    assert r.json()["deliveries"][0]["delivery_id"] == "dl_1"


@pytest.mark.asyncio
async def test_proxies_return_503_when_the_cloud_transport_is_not_wired(
    client, signed_in_user
) -> None:
    """The deferred HTTP transport must surface as a legible 503, not a 500."""
    set_cloud(HttpCloudControlPlane("https://cloud.example.invalid", "k"))
    await _tenant_for(signed_in_user["user"].id, "t_unwired")
    r = await client.get("/api/v1/installs/ingress-urls", cookies=signed_in_user["cookies"])
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "cloud_unavailable"
    set_cloud(InMemoryCloudControlPlane())
