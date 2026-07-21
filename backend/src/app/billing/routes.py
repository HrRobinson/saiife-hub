from __future__ import annotations

import json
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import verified_user
from ..cloud.deps import get_cloud
from ..core.config import settings
from ..core.rate_limit import limiter
from ..db.session import get_db
from ..models.billing import StripeEvent, Subscription
from ..models.tenant import Tenant
from ..models.user import User
from .gateway import get_stripe_gateway
from .service import apply_stripe_event
from .signature import SignatureError, verify_stripe_signature

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


def _err(code: str, message: str, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


@router.get("/subscription")
async def get_subscription(
    user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    subscription = await db.scalar(select(Subscription).where(Subscription.user_id == user.id))
    if subscription is None:
        return {
            "status": "none",
            "current_period_end": None,
            "has_tenant": False,
            "account_token_issued_at": None,
        }
    tenant = await db.scalar(select(Tenant).where(Tenant.subscription_id == subscription.id))
    return {
        "status": subscription.status,
        "current_period_end": (
            subscription.current_period_end.isoformat()
            if subscription.current_period_end
            else None
        ),
        "has_tenant": tenant is not None,
        "account_token_issued_at": (
            tenant.account_token_issued_at.isoformat()
            if tenant is not None and tenant.account_token_issued_at
            else None
        ),
    }


@router.post("/checkout-session")
@limiter.limit("10/minute")
async def create_checkout_session(
    request: Request,
    user: User = Depends(verified_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    subscription = await db.scalar(select(Subscription).where(Subscription.user_id == user.id))
    session = await get_stripe_gateway().create_checkout_session(
        user_id=str(user.id),
        email=user.email,
        price_id=settings.STRIPE_PRICE_ID,
        success_url=f"{settings.APP_URL}/dashboard?subscribed=1",
        cancel_url=f"{settings.APP_URL}/billing?cancelled=1",
        existing_customer_id=subscription.stripe_customer_id if subscription is not None else None,
    )
    if subscription is None:
        db.add(
            Subscription(
                id=uuid.uuid4(),
                user_id=user.id,
                stripe_customer_id=session.customer_id,
                stripe_subscription_id=None,
                status="incomplete",
            )
        )
        await db.commit()
    return {"url": session.url}


@router.post("/portal-session")
@limiter.limit("10/minute")
async def create_portal_session(
    request: Request,
    user: User = Depends(verified_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    subscription = await db.scalar(select(Subscription).where(Subscription.user_id == user.id))
    if subscription is None:
        raise _err("no_subscription", "You do not have a subscription yet.", 404)
    portal = await get_stripe_gateway().create_portal_session(
        customer_id=subscription.stripe_customer_id,
        return_url=f"{settings.APP_URL}/billing",
    )
    return {"url": portal.url}


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Signature-verified, replay-safe entry point for Stripe.

    Order is load-bearing:
      1. verify the signature over the RAW bytes — no state change before this;
      2. claim the event id (PK insert) — a replay collides and short-circuits;
      3. apply the event.
    """
    raw = await request.body()
    try:
        verify_stripe_signature(
            raw,
            request.headers.get("stripe-signature"),
            settings.STRIPE_WEBHOOK_SECRET,
            tolerance_seconds=settings.STRIPE_SIGNATURE_TOLERANCE_SECONDS,
        )
    except SignatureError as exc:
        # Never echo the reason to the caller — log it, return one flat code.
        log.warning("stripe_webhook_rejected", reason=exc.reason)
        raise _err("invalid_signature", "Signature verification failed.", 400) from None

    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        raise _err("invalid_payload", "Webhook body was not JSON.", 400) from None
    if not isinstance(event, dict) or not isinstance(event.get("id"), str):
        raise _err("invalid_payload", "Webhook body had no event id.", 400)

    event_id = event["id"]
    event_type = str(event.get("type", ""))

    # Claim the event id first. A retried delivery collides on the primary key,
    # which is exactly how we detect a replay.
    db.add(StripeEvent(event_id=event_id, event_type=event_type))
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        log.info("stripe_webhook_replay", event_id=event_id, event_type=event_type)
        return {"received": True, "duplicate": True, "action": "ignored"}

    action = await apply_stripe_event(
        db, get_cloud(), event=event, pepper=settings.ACCOUNT_TOKEN_PEPPER
    )
    await db.commit()
    log.info("stripe_webhook_applied", event_id=event_id, event_type=event_type, action=action)
    return {"received": True, "duplicate": False, "action": action}
