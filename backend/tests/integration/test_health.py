import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_returns_ok() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.saiife.localhost"
    ) as c:
        r = await c.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": "test"}


@pytest.mark.asyncio
async def test_unknown_route_returns_error_envelope() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://api.saiife.localhost"
    ) as c:
        r = await c.get("/api/v1/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "http_error"
