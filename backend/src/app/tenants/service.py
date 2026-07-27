"""Tenant lifecycle against saiife-cloud.

Never say "provision" here — cloud already uses that word for Pub/Sub subscription
provisioning. Tenant lifecycle is create / delete.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..cloud.contracts import CreateTenantRequest
from ..cloud.seam import CloudControlPlane
from ..models.billing import Subscription
from ..models.tenant import Tenant
from . import tokens

log = structlog.get_logger(__name__)


def external_ref(subscription: Subscription) -> str:
    """The idempotency key cloud dedupes on. Stable for the subscription's life."""
    return f"hub:{subscription.stripe_subscription_id or subscription.id}"


@dataclass(frozen=True)
class IssuedAccountToken:
    token: str
    """PLAINTEXT — returned to the user exactly once. Never logged or persisted."""
    cloud_tenant_id: str
    issued_at: datetime


async def _load_tenant(db: AsyncSession, subscription: Subscription) -> Tenant | None:
    result: Tenant | None = await db.scalar(
        select(Tenant).where(Tenant.subscription_id == subscription.id)
    )
    return result


async def ensure_tenant(
    db: AsyncSession,
    cloud: CloudControlPlane,
    *,
    subscription: Subscription,
    pepper: str,
) -> Tenant:
    """Create the cloud tenant for this subscription if it does not exist yet.

    Idempotent at BOTH layers: hub short-circuits on the existing Tenant row, and
    cloud dedupes on `externalRef`. A Stripe retry therefore cannot double-create.

    The first account token is minted here so the tenant is never tokenless, but
    its plaintext is discarded — the user reveals a token via `issue_account_token`.
    """
    existing = await _load_tenant(db, subscription)
    if existing is not None:
        return existing

    generated = tokens.generate_account_token()
    token_hash = tokens.hash_account_secret(generated.secret, pepper)
    cloud_tenant = await cloud.create_tenant(
        CreateTenantRequest(
            external_ref=external_ref(subscription),
            tenant_lookup_id=generated.tenant_lookup_id,
            account_token_hash=token_hash,
        )
    )
    tenant = Tenant(
        id=uuid.uuid4(),
        user_id=subscription.user_id,
        subscription_id=subscription.id,
        cloud_tenant_id=cloud_tenant.tenant_id,
        tenant_lookup_id=generated.tenant_lookup_id,
        account_token_hash=token_hash,
        account_token_hash_algo="scrypt",
        account_token_issued_at=None,
    )
    db.add(tenant)
    await db.flush()
    # NEVER log the token or the secret — only that a tenant now exists.
    log.info("tenant_created", cloud_tenant_id=cloud_tenant.tenant_id)
    return tenant


async def issue_account_token(
    db: AsyncSession,
    cloud: CloudControlPlane,
    *,
    subscription: Subscription,
    pepper: str,
) -> IssuedAccountToken:
    """Mint a NEW account token, replace the stored hash, return the plaintext once.

    Calling this a second time is rotation: the previous token stops verifying the
    moment the new hash lands.
    """
    tenant = await ensure_tenant(db, cloud, subscription=subscription, pepper=pepper)

    generated = tokens.generate_account_token()
    token_hash = tokens.hash_account_secret(generated.secret, pepper)
    await cloud.create_tenant(
        CreateTenantRequest(
            external_ref=external_ref(subscription),
            tenant_lookup_id=generated.tenant_lookup_id,
            account_token_hash=token_hash,
        )
    )
    tenant.tenant_lookup_id = generated.tenant_lookup_id
    tenant.account_token_hash = token_hash
    tenant.account_token_hash_algo = "scrypt"
    tenant.account_token_issued_at = datetime.now(timezone.utc)
    await db.flush()
    log.info("account_token_issued", cloud_tenant_id=tenant.cloud_tenant_id)
    return IssuedAccountToken(
        token=generated.token,
        cloud_tenant_id=tenant.cloud_tenant_id,
        issued_at=tenant.account_token_issued_at,
    )


async def remove_tenant(
    db: AsyncSession, cloud: CloudControlPlane, *, subscription: Subscription
) -> None:
    """Delete the cloud tenant and hub's record of it. Idempotent."""
    tenant = await _load_tenant(db, subscription)
    if tenant is None:
        return
    await cloud.delete_tenant(tenant.cloud_tenant_id)
    await db.delete(tenant)
    await db.flush()
    log.info("tenant_deleted", cloud_tenant_id=tenant.cloud_tenant_id)
