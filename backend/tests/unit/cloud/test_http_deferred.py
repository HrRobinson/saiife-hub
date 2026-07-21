import pytest

from app.cloud.contracts import CreateTenantRequest
from app.cloud.deps import configure_default_cloud, get_cloud, set_cloud
from app.cloud.errors import NotWiredError
from app.cloud.http import HttpCloudControlPlane
from app.cloud.mock import InMemoryCloudControlPlane


def test_http_transport_constructs_at_startup() -> None:
    """Constructing must succeed so the app boots; only calls are deferred."""
    plane = HttpCloudControlPlane("https://cloud.example.invalid", "admin-key")
    assert plane.base_url == "https://cloud.example.invalid"


def test_http_transport_rejects_an_empty_base_url() -> None:
    with pytest.raises(ValueError, match="base_url"):
        HttpCloudControlPlane("", "admin-key")


@pytest.mark.asyncio
async def test_every_http_method_raises_not_wired() -> None:
    plane = HttpCloudControlPlane("https://cloud.example.invalid", "admin-key")
    req = CreateTenantRequest(
        external_ref="hub:sub_1",
        tenant_lookup_id="0123456789abcdef01",
        account_token_hash="scrypt$16384$8$1$c2FsdA==$aGFzaA==",
    )
    with pytest.raises(NotWiredError):
        await plane.create_tenant(req)
    with pytest.raises(NotWiredError):
        await plane.delete_tenant("t_x")
    with pytest.raises(NotWiredError):
        await plane.list_ingress_urls("t_x")
    with pytest.raises(NotWiredError):
        await plane.get_delivery_history("t_x")


def test_default_cloud_is_the_mock_when_no_admin_url_is_configured() -> None:
    configure_default_cloud()
    assert isinstance(get_cloud(), InMemoryCloudControlPlane)


def test_set_cloud_replaces_the_active_control_plane() -> None:
    replacement = InMemoryCloudControlPlane()
    set_cloud(replacement)
    assert get_cloud() is replacement
