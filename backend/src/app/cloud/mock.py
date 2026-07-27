"""In-memory CloudControlPlane. EVERY test runs against this — no network.

Mirrors saiife-cloud's own `packages/shared/src/mocks.ts` pattern: deterministic,
inspectable, and recording every call so a test can prove idempotency.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from .contracts import CloudTenant, CreateTenantRequest, DeliveryRecord, IngressUrl


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class InMemoryCloudControlPlane:
    def __init__(self) -> None:
        self.tenants: dict[str, CloudTenant] = {}
        self._by_external_ref: dict[str, str] = {}
        self._ingress: dict[str, list[IngressUrl]] = {}
        self._deliveries: dict[str, list[DeliveryRecord]] = {}
        self.create_calls: list[CreateTenantRequest] = []
        self.delete_calls: list[str] = []

    # --- seam methods ----------------------------------------------------

    async def create_tenant(self, request: CreateTenantRequest) -> CloudTenant:
        self.create_calls.append(request)
        existing_id = self._by_external_ref.get(request.external_ref)
        if existing_id is not None:
            # Same externalRef => rotate in place, same tenantId. Never a second tenant.
            previous = self.tenants[existing_id]
            rotated = CloudTenant(
                tenant_id=previous.tenant_id,
                tenant_lookup_id=request.tenant_lookup_id,
                status=previous.status,
                created_at=previous.created_at,
            )
            self.tenants[existing_id] = rotated
            return rotated

        tenant_id = "t_" + secrets.token_urlsafe(12).replace("=", "")
        tenant = CloudTenant(
            tenant_id=tenant_id,
            tenant_lookup_id=request.tenant_lookup_id,
            status="active",
            created_at=_now_iso(),
        )
        self.tenants[tenant_id] = tenant
        self._by_external_ref[request.external_ref] = tenant_id
        self._ingress.setdefault(tenant_id, [])
        self._deliveries.setdefault(tenant_id, [])
        return tenant

    async def delete_tenant(self, tenant_id: str) -> None:
        self.delete_calls.append(tenant_id)
        self.tenants.pop(tenant_id, None)
        self._ingress.pop(tenant_id, None)
        self._deliveries.pop(tenant_id, None)
        for ref, tid in list(self._by_external_ref.items()):
            if tid == tenant_id:
                del self._by_external_ref[ref]

    async def list_ingress_urls(self, tenant_id: str) -> list[IngressUrl]:
        return list(self._ingress.get(tenant_id, []))

    async def get_delivery_history(
        self, tenant_id: str, limit: int = 50
    ) -> list[DeliveryRecord]:
        records = self._deliveries.get(tenant_id, [])
        return list(reversed(records))[:limit]

    # --- test affordances ------------------------------------------------

    def seed_ingress_url(self, tenant_id: str, ingress: IngressUrl) -> None:
        self._ingress.setdefault(tenant_id, []).append(ingress)

    def seed_delivery(self, tenant_id: str, delivery: DeliveryRecord) -> None:
        self._deliveries.setdefault(tenant_id, []).append(delivery)
