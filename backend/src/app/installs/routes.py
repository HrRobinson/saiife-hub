from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.deps import verified_user
from ..cloud.deps import get_cloud
from ..cloud.errors import CloudError, NotWiredError
from ..db.session import get_db
from ..models.install import Install
from ..models.tenant import Tenant
from ..models.user import User

router = APIRouter(prefix="/api/v1/installs", tags=["installs"])
log = structlog.get_logger(__name__)


class CreateInstallRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


def _err(code: str, message: str, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _install_out(i: Install) -> dict[str, Any]:
    return {
        "id": str(i.id),
        "name": i.name,
        "created_at": i.created_at.isoformat(),
        "last_seen_at": i.last_seen_at.isoformat() if i.last_seen_at else None,
    }


async def _require_tenant(db: AsyncSession, user: User) -> Tenant:
    tenant = await db.scalar(select(Tenant).where(Tenant.user_id == user.id))
    if tenant is None:
        raise _err("no_tenant", "No hosted tenant exists for this account yet.", 404)
    return tenant


@router.get("")
async def list_installs(
    user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(Install).where(Install.user_id == user.id).order_by(Install.created_at)
        )
    ).scalars().all()
    return [_install_out(i) for i in rows]


@router.post("", status_code=201)
async def create_install(
    body: CreateInstallRequest,
    user: User = Depends(verified_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    install = Install(id=uuid.uuid4(), user_id=user.id, name=body.name)
    db.add(install)
    await db.commit()
    await db.refresh(install)
    return _install_out(install)


@router.delete("/{install_id}", status_code=204)
async def delete_install(
    install_id: uuid.UUID,
    user: User = Depends(verified_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    install = await db.scalar(
        select(Install).where(Install.id == install_id, Install.user_id == user.id)
    )
    if install is None:
        raise _err("install_not_found", "Install not found.", 404)
    await db.delete(install)
    await db.commit()


@router.get("/ingress-urls")
async def list_ingress_urls(
    user: User = Depends(verified_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    tenant = await _require_tenant(db, user)
    try:
        urls = await get_cloud().list_ingress_urls(tenant.cloud_tenant_id)
    except NotWiredError as exc:
        log.warning("cloud_not_wired", transport=exc.transport)
        raise _err(
            "cloud_unavailable",
            "Hosted ingress is not available yet — the relay is not connected.",
            503,
        ) from None
    except CloudError as exc:
        log.warning("cloud_error", code=exc.code)
        raise _err("cloud_unavailable", "The relay could not be reached — retry shortly.", 503) from None
    return {"ingress_urls": [u.to_api() for u in urls]}


@router.get("/deliveries")
async def list_deliveries(
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(verified_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    tenant = await _require_tenant(db, user)
    try:
        deliveries = await get_cloud().get_delivery_history(tenant.cloud_tenant_id, limit=limit)
    except NotWiredError as exc:
        log.warning("cloud_not_wired", transport=exc.transport)
        raise _err(
            "cloud_unavailable",
            "Delivery history is not available yet — the relay is not connected.",
            503,
        ) from None
    except CloudError as exc:
        log.warning("cloud_error", code=exc.code)
        raise _err("cloud_unavailable", "The relay could not be reached — retry shortly.", 503) from None
    return {"deliveries": [d.to_api() for d in deliveries]}
