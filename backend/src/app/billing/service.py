"""Applies a VERIFIED Stripe event to subscription and tenant state.

The caller must have verified the signature and rejected replays before calling
this. Nothing here re-checks authenticity.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..cloud.seam import CloudControlPlane
from ..models.billing import Subscription
from ..tenants.service import ensure_tenant, remove_tenant

log = structlog.get_logger(__name__)


async def _find_subscription(
    db: AsyncSession, obj: dict[str, Any]
) -> Subscription | None:
    """Locate the hub subscription from a Stripe object, most specific first."""
    stripe_subscription_id = obj.get("subscription") or obj.get("id")
    if isinstance(stripe_subscription_id, str):
        found = await db.scalar(
            select(Subscription).where(
                Subscription.stripe_subscription_id == stripe_subscription_id
            )
        )
        if found is not None:
            return found
    customer = obj.get("customer")
    if isinstance(customer, str):
        by_customer: Subscription | None = await db.scalar(
            select(Subscription).where(Subscription.stripe_customer_id == customer)
        )
        return by_customer
    return None


def _period_end(obj: dict[str, Any]) -> datetime | None:
    raw = obj.get("current_period_end")
    if isinstance(raw, int):
        return datetime.fromtimestamp(raw, tz=timezone.utc)
    return None


async def apply_stripe_event(
    db: AsyncSession,
    cloud: CloudControlPlane,
    *,
    event: dict[str, Any],
    pepper: str,
) -> str:
    """Return the action taken: tenant_created | tenant_deleted | subscription_updated
    | unknown_subscription | ignored."""
    event_type = str(event.get("type", ""))
    obj = event.get("data", {}).get("object", {})
    if not isinstance(obj, dict):
        return "ignored"

    if event_type == "checkout.session.completed":
        subscription = await _find_subscription(db, obj)
        if subscription is None:
            log.warning("stripe_event_unknown_subscription", event_type=event_type)
            return "unknown_subscription"
        stripe_subscription_id = obj.get("subscription")
        if isinstance(stripe_subscription_id, str):
            subscription.stripe_subscription_id = stripe_subscription_id
        subscription.status = "active"
        subscription.updated_at = datetime.now(timezone.utc)
        await db.flush()
        await ensure_tenant(db, cloud, subscription=subscription, pepper=pepper)
        return "tenant_created"

    if event_type == "customer.subscription.deleted":
        subscription = await _find_subscription(db, obj)
        if subscription is None:
            log.warning("stripe_event_unknown_subscription", event_type=event_type)
            return "unknown_subscription"
        subscription.status = "canceled"
        subscription.updated_at = datetime.now(timezone.utc)
        await remove_tenant(db, cloud, subscription=subscription)
        return "tenant_deleted"

    if event_type == "customer.subscription.updated":
        subscription = await _find_subscription(db, obj)
        if subscription is None:
            return "unknown_subscription"
        status = obj.get("status")
        if isinstance(status, str):
            subscription.status = "active" if status in {"active", "trialing"} else status
        subscription.current_period_end = _period_end(obj) or subscription.current_period_end
        subscription.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return "subscription_updated"

    return "ignored"
