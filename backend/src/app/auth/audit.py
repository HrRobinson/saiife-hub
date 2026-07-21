from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any, Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import AuthEvent


async def log_event(
    db: AsyncSession,
    *,
    user_id: Optional[uuid.UUID],
    event_type: str,
    request: Optional[Request] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> None:
    ip = None
    ua = None
    if request is not None:
        ua = request.headers.get("user-agent")
        if request.client:
            ip = request.client.host
    db.add(
        AuthEvent(
            user_id=user_id,
            event_type=event_type,
            ip=ip,
            user_agent=ua,
            metadata_=dict(metadata) if metadata else None,
        )
    )
    # Caller commits.
