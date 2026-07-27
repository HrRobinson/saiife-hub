"""Wire shapes for the saiife-cloud admin API.

saiife-cloud is TypeScript and uses camelCase on the wire; hub is Python and uses
snake_case internally. Every dataclass here owns exactly one translation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ADMIN_API_ROUTES: dict[str, tuple[str, str]] = {
    "create_tenant": ("POST", "/admin/v1/tenants"),
    "delete_tenant": ("DELETE", "/admin/v1/tenants/{tenant_id}"),
    "list_ingress_urls": ("GET", "/admin/v1/tenants/{tenant_id}/ingress-urls"),
    "get_delivery_history": ("GET", "/admin/v1/tenants/{tenant_id}/deliveries"),
}


@dataclass(frozen=True)
class CreateTenantRequest:
    """Create-or-rotate. IDEMPOTENT on `external_ref`.

    If no tenant carries `external_ref`, cloud creates one. If one does, cloud
    REPLACES its lookup id + account token hash (that is token rotation) and
    returns the SAME tenantId. A second call must never yield a second tenant.
    """

    external_ref: str
    tenant_lookup_id: str
    account_token_hash: str
    account_token_hash_algo: str = "scrypt"

    def to_wire(self) -> dict[str, Any]:
        return {
            "externalRef": self.external_ref,
            "tenantLookupId": self.tenant_lookup_id,
            "accountTokenHash": self.account_token_hash,
            "accountTokenHashAlgo": self.account_token_hash_algo,
        }


@dataclass(frozen=True)
class CloudTenant:
    tenant_id: str
    tenant_lookup_id: str
    status: str
    created_at: str

    @classmethod
    def from_wire(cls, raw: dict[str, Any]) -> CloudTenant:
        return cls(
            tenant_id=str(raw["tenantId"]),
            tenant_lookup_id=str(raw["tenantLookupId"]),
            status=str(raw["status"]),
            created_at=str(raw["createdAt"]),
        )


@dataclass(frozen=True)
class IngressUrl:
    id: str
    integration: str
    url: str
    created_at: str

    @classmethod
    def from_wire(cls, raw: dict[str, Any]) -> IngressUrl:
        return cls(
            id=str(raw["id"]),
            integration=str(raw["integration"]),
            url=str(raw["url"]),
            created_at=str(raw["createdAt"]),
        )

    def to_api(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "integration": self.integration,
            "url": self.url,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class DeliveryRecord:
    delivery_id: str
    ingress_id: str
    integration: str
    received_at: str
    status: str

    @classmethod
    def from_wire(cls, raw: dict[str, Any]) -> DeliveryRecord:
        return cls(
            delivery_id=str(raw["deliveryId"]),
            ingress_id=str(raw["ingressId"]),
            integration=str(raw["integration"]),
            received_at=str(raw["receivedAt"]),
            status=str(raw["status"]),
        )

    def to_api(self) -> dict[str, Any]:
        return {
            "delivery_id": self.delivery_id,
            "ingress_id": self.ingress_id,
            "integration": self.integration,
            "received_at": self.received_at,
            "status": self.status,
        }
