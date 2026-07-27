import pytest

from app.billing.gateway import (
    MockStripeGateway,
    configure_default_stripe_gateway,
    get_stripe_gateway,
    set_stripe_gateway,
)


@pytest.fixture(autouse=True)
def _no_stripe_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "")


@pytest.mark.asyncio
async def test_mock_checkout_session_is_deterministic_and_records_the_call() -> None:
    gw = MockStripeGateway()
    session = await gw.create_checkout_session(
        user_id="11111111-1111-1111-1111-111111111111",
        email="alice@example.com",
        price_id="price_test",
        success_url="https://app.example.invalid/billing?ok=1",
        cancel_url="https://app.example.invalid/billing?cancelled=1",
    )
    assert session.id == "cs_mock_1"
    assert session.customer_id == "cus_mock_1"
    assert session.url == "https://checkout.stripe.invalid/mock/cs_mock_1"
    assert gw.checkout_calls[0]["email"] == "alice@example.com"
    assert gw.checkout_calls[0]["price_id"] == "price_test"


@pytest.mark.asyncio
async def test_mock_ids_increment_per_call() -> None:
    gw = MockStripeGateway()
    first = await gw.create_checkout_session(
        user_id="u", email="a@example.com", price_id="p",
        success_url="https://x.invalid", cancel_url="https://x.invalid",
    )
    second = await gw.create_checkout_session(
        user_id="u", email="a@example.com", price_id="p",
        success_url="https://x.invalid", cancel_url="https://x.invalid",
    )
    assert (first.id, second.id) == ("cs_mock_1", "cs_mock_2")


@pytest.mark.asyncio
async def test_mock_portal_session_returns_a_url_and_records_the_call() -> None:
    gw = MockStripeGateway()
    portal = await gw.create_portal_session(
        customer_id="cus_mock_1", return_url="https://app.example.invalid/billing"
    )
    assert portal.url == "https://billing.stripe.invalid/mock/cus_mock_1"
    assert gw.portal_calls == [
        {"customer_id": "cus_mock_1", "return_url": "https://app.example.invalid/billing"}
    ]


def test_default_gateway_is_the_mock_without_a_secret_key() -> None:
    configure_default_stripe_gateway()
    assert isinstance(get_stripe_gateway(), MockStripeGateway)


def test_set_gateway_replaces_the_active_gateway() -> None:
    replacement = MockStripeGateway()
    set_stripe_gateway(replacement)
    assert get_stripe_gateway() is replacement
