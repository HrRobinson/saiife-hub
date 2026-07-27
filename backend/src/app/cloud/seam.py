"""The single seam between hub and saiife-cloud.

Deliberately NOT named "provision": saiife-cloud already uses
`SubscriptionProvisioner` for Pub/Sub subscription provisioning, which is a
different thing entirely.
"""
from __future__ import annotations

from typing import Protocol

from .contracts import CloudTenant, CreateTenantRequest, DeliveryRecord, IngressUrl


class CloudControlPlane(Protocol):
    async def create_tenant(self, request: CreateTenantRequest) -> CloudTenant:
        """Create-or-rotate a tenant. Idempotent on `request.external_ref`."""
        ...

    async def delete_tenant(self, tenant_id: str) -> None:
        """Remove a tenant and its ingress records. Idempotent: deleting an
        unknown tenant is a no-op, never an error."""
        ...

    async def list_ingress_urls(self, tenant_id: str) -> list[IngressUrl]:
        ...

    async def get_delivery_history(
        self, tenant_id: str, limit: int = 50
    ) -> list[DeliveryRecord]:
        ...
