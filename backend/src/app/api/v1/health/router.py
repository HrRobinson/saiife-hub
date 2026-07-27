from typing import Any

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(prefix="/api/v1/health", tags=["health"])


@router.get("")
async def health() -> dict[str, Any]:
    return {"status": "ok", "version": settings.APP_VERSION}
