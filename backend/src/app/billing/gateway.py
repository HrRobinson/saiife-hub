"""Stripe API access behind a seam so every test runs offline.

Only OUTBOUND calls live here. Inbound webhooks are verified by
`app.billing.signature` and applied by `app.billing.service`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..core.config import settings


@dataclass(frozen=True)
class CheckoutSession:
    id: str
    url: str
    customer_id: str


@dataclass(frozen=True)
class PortalSession:
    url: str


class StripeGateway(Protocol):
    async def create_checkout_session(
        self,
        *,
        user_id: str,
        email: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        existing_customer_id: str | None = None,
    ) -> CheckoutSession: ...

    async def create_portal_session(
        self, *, customer_id: str, return_url: str
    ) -> PortalSession: ...


class MockStripeGateway:
    """Deterministic, inspectable, and never touches the network."""

    def __init__(self) -> None:
        self.checkout_calls: list[dict[str, Any]] = []
        self.portal_calls: list[dict[str, Any]] = []
        self._counter = 0

    async def create_checkout_session(
        self,
        *,
        user_id: str,
        email: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        existing_customer_id: str | None = None,
    ) -> CheckoutSession:
        self._counter += 1
        n = self._counter
        self.checkout_calls.append(
            {
                "user_id": user_id,
                "email": email,
                "price_id": price_id,
                "success_url": success_url,
                "cancel_url": cancel_url,
                "existing_customer_id": existing_customer_id,
            }
        )
        return CheckoutSession(
            id=f"cs_mock_{n}",
            url=f"https://checkout.stripe.invalid/mock/cs_mock_{n}",
            customer_id=existing_customer_id or f"cus_mock_{n}",
        )

    async def create_portal_session(
        self, *, customer_id: str, return_url: str
    ) -> PortalSession:
        self.portal_calls.append({"customer_id": customer_id, "return_url": return_url})
        return PortalSession(url=f"https://billing.stripe.invalid/mock/{customer_id}")


class LiveStripeGateway:
    """The real Stripe transport. Constructed only when a secret key is set."""

    def __init__(self, secret_key: str) -> None:
        if not secret_key:
            raise ValueError("LiveStripeGateway requires a Stripe secret key.")
        import stripe

        self._stripe = stripe
        self._client = stripe.StripeClient(secret_key)

    async def create_checkout_session(
        self,
        *,
        user_id: str,
        email: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        existing_customer_id: str | None = None,
    ) -> CheckoutSession:
        if existing_customer_id:
            session = self._client.checkout.sessions.create(
                params={
                    "mode": "subscription",
                    "line_items": [{"price": price_id, "quantity": 1}],
                    "customer": existing_customer_id,
                    "client_reference_id": user_id,
                    "success_url": success_url,
                    "cancel_url": cancel_url,
                    # Echoed back on the webhook so the handler can find the user
                    # without trusting anything else in the payload.
                    "metadata": {"hub_user_id": user_id},
                    "subscription_data": {"metadata": {"hub_user_id": user_id}},
                }
            )
        else:
            session = self._client.checkout.sessions.create(
                params={
                    "mode": "subscription",
                    "line_items": [{"price": price_id, "quantity": 1}],
                    "customer_email": email,
                    "client_reference_id": user_id,
                    "success_url": success_url,
                    "cancel_url": cancel_url,
                    # Echoed back on the webhook so the handler can find the user
                    # without trusting anything else in the payload.
                    "metadata": {"hub_user_id": user_id},
                    "subscription_data": {"metadata": {"hub_user_id": user_id}},
                }
            )
        customer = session.customer
        customer_id = customer if isinstance(customer, str) else getattr(customer, "id", "")
        return CheckoutSession(id=session.id, url=session.url or "", customer_id=customer_id or "")

    async def create_portal_session(
        self, *, customer_id: str, return_url: str
    ) -> PortalSession:
        session = self._client.billing_portal.sessions.create(
            params={"customer": customer_id, "return_url": return_url}
        )
        return PortalSession(url=session.url)


_gateway: StripeGateway = MockStripeGateway()


def get_stripe_gateway() -> StripeGateway:
    return _gateway


def set_stripe_gateway(g: StripeGateway) -> None:
    global _gateway
    _gateway = g


def configure_default_stripe_gateway() -> None:
    if settings.STRIPE_SECRET_KEY:
        set_stripe_gateway(LiveStripeGateway(settings.STRIPE_SECRET_KEY))
    else:
        set_stripe_gateway(MockStripeGateway())
