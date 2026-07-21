from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import verified_user
from ..core.config import settings
from ..core.rate_limit import limiter
from ..db.session import get_db
from ..models.billing import Subscription
from ..models.tenant import Tenant
from ..models.user import User
from .gateway import get_stripe_gateway

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
