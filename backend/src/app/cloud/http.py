"""DEFERRED live transport for the saiife-cloud admin API.

saiife-cloud exposes exactly two routes today — `/v1/ingress-urls` and
`/v1/drain-token` — both authenticated AS an existing tenant. There is no route
that creates one, and hub cannot authenticate as a tenant anyway because it stores
only the token HASH. The admin API this class targets is specified in
docs/2026-07-21-saiife-cloud-admin-api-contract.md and does not exist yet.

Constructing this class succeeds so the app boots; every call raises NotWiredError.
When cloud implements the contract, replace each `_not_wired()` with the httpx call
already sketched in the docstring of each method.
"""
from __future__ import annotations

from typing import NoReturn

from .contracts import ADMIN_API_ROUTES, CloudTenant, CreateTenantRequest, DeliveryRecord, IngressUrl

_TRANSPORT = "saiife-cloud admin API transport"


class HttpCloudControlPlane:
    def __init__(self, base_url: str, api_key: str) -> None:
        if not base_url:
            raise ValueError("HttpCloudControlPlane requires a non-empty base_url.")
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key

    def _not_wired(self) -> NoReturn:
        from .errors import NotWiredError

        raise NotWiredError(_TRANSPORT)

    async def create_tenant(self, request: CreateTenantRequest) -> CloudTenant:
        """POST {base_url}/admin/v1/tenants, body `request.to_wire()`,
        `Authorization: Bearer <api_key>`, `Idempotency-Key: <external_ref>`."""
        assert ADMIN_API_ROUTES["create_tenant"] == ("POST", "/admin/v1/tenants")
        self._not_wired()

    async def delete_tenant(self, tenant_id: str) -> None:
        """DELETE {base_url}/admin/v1/tenants/{tenant_id}. 404 is treated as success."""
        self._not_wired()

    async def list_ingress_urls(self, tenant_id: str) -> list[IngressUrl]:
        """GET {base_url}/admin/v1/tenants/{tenant_id}/ingress-urls
        -> `{"ingressUrls": IngressUrl[]}`."""
        self._not_wired()

    async def get_delivery_history(
        self, tenant_id: str, limit: int = 50
    ) -> list[DeliveryRecord]:
        """GET {base_url}/admin/v1/tenants/{tenant_id}/deliveries?limit=N
        -> `{"deliveries": DeliveryRecord[]}`."""
        self._not_wired()
