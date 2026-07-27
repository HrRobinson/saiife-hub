from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import verified_user
from ..cloud.deps import get_cloud
from ..core.config import settings
from ..core.rate_limit import limiter
from ..db.session import get_db
from ..models.billing import Subscription
from ..models.tenant import Tenant
from ..models.user import User
from .service import issue_account_token

router = APIRouter(prefix="/api/v1/tenants", tags=["tenants"])

_ENTITLED_STATUSES = frozenset({"active", "trialing", "past_due"})


def _err(code: str, message: str, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


@router.get("/me")
async def get_tenant(
    user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Tenant metadata only. The account token is NEVER returned here."""
    tenant = await db.scalar(select(Tenant).where(Tenant.user_id == user.id))
    if tenant is None:
        raise _err("no_tenant", "No hosted tenant exists for this account yet.", 404)
    return {
        "cloud_tenant_id": tenant.cloud_tenant_id,
        "tenant_lookup_id": tenant.tenant_lookup_id,
        "account_token_issued_at": (
            tenant.account_token_issued_at.isoformat()
            if tenant.account_token_issued_at
            else None
        ),
    }


@router.post("/account-token", status_code=201)
@limiter.limit("5/hour")
async def issue_token(
    request: Request,
    user: User = Depends(verified_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Mint a new account token and return the plaintext EXACTLY ONCE.

    Calling this again is rotation: the previous token stops working immediately.
    Only the scrypt hash is stored; the plaintext is never logged or re-readable.
    """
    subscription = await db.scalar(select(Subscription).where(Subscription.user_id == user.id))
    if subscription is None or subscription.status not in _ENTITLED_STATUSES:
        raise _err(
            "subscription_required",
            "An active subscription is required to issue an account token.",
            402,
        )
    issued = await issue_account_token(
        db, get_cloud(), subscription=subscription, pepper=settings.ACCOUNT_TOKEN_PEPPER
    )
    await db.commit()
    return {
        "token": issued.token,
        "cloud_tenant_id": issued.cloud_tenant_id,
        "issued_at": issued.issued_at.isoformat(),
    }
