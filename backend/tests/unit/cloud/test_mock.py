import pytest

from app.cloud.contracts import CreateTenantRequest, DeliveryRecord, IngressUrl
from app.cloud.mock import InMemoryCloudControlPlane


def _req(external_ref: str = "hub:sub_1", lookup: str = "0123456789abcdef01") -> CreateTenantRequest:
    return CreateTenantRequest(
        external_ref=external_ref,
        tenant_lookup_id=lookup,
        account_token_hash="scrypt$16384$8$1$c2FsdA==$aGFzaA==",
    )


@pytest.mark.asyncio
async def test_create_tenant_returns_an_active_tenant_with_a_t_prefixed_id() -> None:
    cloud = InMemoryCloudControlPlane()
    tenant = await cloud.create_tenant(_req())
    assert tenant.tenant_id.startswith("t_")
    assert tenant.tenant_lookup_id == "0123456789abcdef01"
    assert tenant.status == "active"
    assert cloud.create_calls == [_req()]


@pytest.mark.asyncio
async def test_create_tenant_is_idempotent_on_external_ref() -> None:
    """The contract's core guarantee: a Stripe retry must not double-create."""
    cloud = InMemoryCloudControlPlane()
    first = await cloud.create_tenant(_req())
    second = await cloud.create_tenant(_req())
    assert first.tenant_id == second.tenant_id
    assert len(cloud.tenants) == 1


@pytest.mark.asyncio
async def test_create_tenant_with_same_external_ref_rotates_the_token_hash() -> None:
    cloud = InMemoryCloudControlPlane()
    first = await cloud.create_tenant(_req(lookup="aaaaaaaaaaaaaaaaaa"))
    rotated = await cloud.create_tenant(_req(lookup="bbbbbbbbbbbbbbbbbb"))
    assert rotated.tenant_id == first.tenant_id
    assert rotated.tenant_lookup_id == "bbbbbbbbbbbbbbbbbb"
    assert cloud.tenants[first.tenant_id].tenant_lookup_id == "bbbbbbbbbbbbbbbbbb"


@pytest.mark.asyncio
async def test_delete_tenant_removes_it_and_is_idempotent() -> None:
    cloud = InMemoryCloudControlPlane()
    tenant = await cloud.create_tenant(_req())
    await cloud.delete_tenant(tenant.tenant_id)
    assert cloud.tenants == {}
    await cloud.delete_tenant(tenant.tenant_id)  # no raise
    assert cloud.delete_calls == [tenant.tenant_id, tenant.tenant_id]


@pytest.mark.asyncio
async def test_list_ingress_urls_and_delivery_history_are_scoped_to_the_tenant() -> None:
    cloud = InMemoryCloudControlPlane()
    a = await cloud.create_tenant(_req("hub:sub_a", "aaaaaaaaaaaaaaaaaa"))
    b = await cloud.create_tenant(_req("hub:sub_b", "bbbbbbbbbbbbbbbbbb"))
    cloud.seed_ingress_url(
        a.tenant_id,
        IngressUrl(
            id="ig_a", integration="stripe",
            url="https://wh.example.invalid/wh/ig_a", created_at="2026-07-21T10:00:00.000Z",
        ),
    )
    cloud.seed_delivery(
        a.tenant_id,
        DeliveryRecord(
            delivery_id="dl_a", ingress_id="ig_a", integration="stripe",
            received_at="2026-07-21T10:00:01.000Z", status="published",
        ),
    )
    assert [u.id for u in await cloud.list_ingress_urls(a.tenant_id)] == ["ig_a"]
    assert await cloud.list_ingress_urls(b.tenant_id) == []
    assert [d.delivery_id for d in await cloud.get_delivery_history(a.tenant_id)] == ["dl_a"]
    assert await cloud.get_delivery_history(b.tenant_id) == []


@pytest.mark.asyncio
async def test_delivery_history_honours_the_limit_newest_first() -> None:
    cloud = InMemoryCloudControlPlane()
    t = await cloud.create_tenant(_req())
    for i in range(5):
        cloud.seed_delivery(
            t.tenant_id,
            DeliveryRecord(
                delivery_id=f"dl_{i}", ingress_id="ig_a", integration="stripe",
                received_at=f"2026-07-21T10:00:0{i}.000Z", status="published",
            ),
        )
    got = await cloud.get_delivery_history(t.tenant_id, limit=2)
    assert [d.delivery_id for d in got] == ["dl_4", "dl_3"]
