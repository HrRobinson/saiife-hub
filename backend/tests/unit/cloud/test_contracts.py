"""The hub half of the saiife-cloud admin contract, pinned as data.

If these assertions change, docs/2026-07-21-saiife-cloud-admin-api-contract.md
must change with them — the doc is the deliverable saiife-cloud implements.
"""
from dataclasses import asdict

from app.cloud.contracts import (
    ADMIN_API_ROUTES,
    CloudTenant,
    CreateTenantRequest,
    DeliveryRecord,
    IngressUrl,
)
from app.cloud.errors import NotWiredError


def test_create_tenant_request_serialises_to_the_pinned_wire_shape() -> None:
    req = CreateTenantRequest(
        external_ref="hub:sub_123",
        tenant_lookup_id="0123456789abcdef01",
        account_token_hash="scrypt$16384$8$1$c2FsdA==$aGFzaA==",
    )
    assert asdict(req) == {
        "external_ref": "hub:sub_123",
        "tenant_lookup_id": "0123456789abcdef01",
        "account_token_hash": "scrypt$16384$8$1$c2FsdA==$aGFzaA==",
        "account_token_hash_algo": "scrypt",
    }
    assert req.to_wire() == {
        "externalRef": "hub:sub_123",
        "tenantLookupId": "0123456789abcdef01",
        "accountTokenHash": "scrypt$16384$8$1$c2FsdA==$aGFzaA==",
        "accountTokenHashAlgo": "scrypt",
    }


def test_cloud_tenant_parses_the_pinned_camelcase_response() -> None:
    tenant = CloudTenant.from_wire(
        {
            "tenantId": "t_abc",
            "tenantLookupId": "0123456789abcdef01",
            "status": "active",
            "createdAt": "2026-07-21T10:00:00.000Z",
        }
    )
    assert tenant == CloudTenant(
        tenant_id="t_abc",
        tenant_lookup_id="0123456789abcdef01",
        status="active",
        created_at="2026-07-21T10:00:00.000Z",
    )


def test_ingress_url_and_delivery_record_parse_their_pinned_shapes() -> None:
    url = IngressUrl.from_wire(
        {
            "id": "ig_x",
            "integration": "stripe",
            "url": "https://wh.example.invalid/wh/ig_x",
            "createdAt": "2026-07-21T10:00:00.000Z",
        }
    )
    assert url.integration == "stripe"
    assert url.url == "https://wh.example.invalid/wh/ig_x"

    delivery = DeliveryRecord.from_wire(
        {
            "deliveryId": "dl_1",
            "ingressId": "ig_x",
            "integration": "stripe",
            "receivedAt": "2026-07-21T10:00:01.000Z",
            "status": "published",
        }
    )
    assert delivery.delivery_id == "dl_1"
    assert delivery.status == "published"


def test_admin_routes_are_pinned() -> None:
    assert ADMIN_API_ROUTES == {
        "create_tenant": ("POST", "/admin/v1/tenants"),
        "delete_tenant": ("DELETE", "/admin/v1/tenants/{tenant_id}"),
        "list_ingress_urls": ("GET", "/admin/v1/tenants/{tenant_id}/ingress-urls"),
        "get_delivery_history": ("GET", "/admin/v1/tenants/{tenant_id}/deliveries"),
    }


def test_not_wired_error_names_the_transport_and_stays_legible() -> None:
    err = NotWiredError("saiife-cloud admin API transport")
    assert err.transport == "saiife-cloud admin API transport"
    assert "not wired yet" in str(err)
    assert "in-memory mock" in str(err)
