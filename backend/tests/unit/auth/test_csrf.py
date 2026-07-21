import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_post_without_csrf_header_rejected() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.saiife.localhost"
    ) as c:
        r = await c.post("/api/v1/tenants/account-token", json={}, cookies={"csrf_token": "abc"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_missing"


@pytest.mark.asyncio
async def test_post_with_mismatched_csrf_rejected() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.saiife.localhost"
    ) as c:
        r = await c.post(
            "/api/v1/tenants/account-token",
            json={},
            cookies={"csrf_token": "abc"},
            headers={"X-CSRF-Token": "different"},
        )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_mismatch"


@pytest.mark.asyncio
async def test_get_bypasses_csrf() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.saiife.localhost"
    ) as c:
        r = await c.get("/api/v1/health")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_stripe_webhook_is_csrf_exempt() -> None:
    """Stripe cannot carry our CSRF header; the webhook authenticates by signature."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.saiife.localhost"
    ) as c:
        r = await c.post("/api/v1/billing/webhook", content=b"{}")
    assert r.status_code != 403
