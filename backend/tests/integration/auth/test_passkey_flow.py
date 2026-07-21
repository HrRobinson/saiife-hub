import uuid

import pytest

from app.db.session import SessionLocal
from app.models.user import Passkey


@pytest.mark.asyncio
async def test_register_start_requires_a_session(client) -> None:
    # This route is CSRF-protected (it is not in the CSRF-exempt list, unlike
    # login/start), so a request must carry a matching double-submit token to
    # even reach the auth dependency — otherwise the CSRF middleware's 403
    # masks the 401 this test means to exercise. A signed-in browser always
    # has the CSRF cookie already; only the session cookie is missing here.
    r = await client.post(
        "/api/v1/auth/passkey/register/start",
        cookies={"csrf_token": "no-session-csrf"},
        headers={"X-CSRF-Token": "no-session-csrf"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_register_start_returns_challenge_and_options(client, signed_in_user) -> None:
    r = await client.post(
        "/api/v1/auth/passkey/register/start",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    assert r.status_code == 200
    body = r.json()
    assert "challenge_id" in body
    assert body["options"]["rp"]["id"] == "saiife.localhost"
    assert "challenge" in body["options"]


@pytest.mark.asyncio
async def test_login_start_is_public_and_allows_discoverable_credentials(client) -> None:
    r = await client.post("/api/v1/auth/passkey/login/start")
    assert r.status_code == 200
    options = r.json()["options"]
    assert "challenge" in options
    # Discoverable-credentials flow: no credential is pinned. py_webauthn may emit
    # an empty list or omit the key entirely; both mean "any registered passkey".
    assert options.get("allowCredentials", []) == []


@pytest.mark.asyncio
async def test_list_rename_and_delete_passkey(client, signed_in_user) -> None:
    user = signed_in_user["user"]
    pk_id = uuid.uuid4()
    async with SessionLocal() as db:
        db.add(
            Passkey(
                id=pk_id,
                user_id=user.id,
                credential_id=b"cred-1",
                public_key=b"pk-1",
                sign_count=0,
                name="Laptop",
            )
        )
        await db.commit()

    listed = await client.get("/api/v1/auth/passkeys", cookies=signed_in_user["cookies"])
    assert listed.status_code == 200
    assert [p["name"] for p in listed.json()] == ["Laptop"]

    renamed = await client.patch(
        f"/api/v1/auth/passkeys/{pk_id}",
        json={"name": "Work laptop"},
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Work laptop"

    deleted = await client.delete(
        f"/api/v1/auth/passkeys/{pk_id}",
        cookies=signed_in_user["cookies"],
        headers={"X-CSRF-Token": signed_in_user["csrf"]},
    )
    assert deleted.status_code == 204

    listed_again = await client.get("/api/v1/auth/passkeys", cookies=signed_in_user["cookies"])
    assert listed_again.json() == []
