from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class Tenant(Base):
    """Hub's record of a tenant that exists in saiife-cloud.

    `account_token_hash` is the ONLY account-token material stored anywhere in
    hub. The plaintext is shown once at issuance and never persisted or logged.
    `account_token_issued_at` is None while a token exists in cloud but has never
    been revealed to the user (the webhook-created first token), which is what
    the dashboard uses to prompt an issuance.
    """

    __tablename__ = "tenants"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    cloud_tenant_id: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    tenant_lookup_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    account_token_hash: Mapped[str] = mapped_column(Text(), nullable=False)
    account_token_hash_algo: Mapped[str] = mapped_column(
        String(20), nullable=False, default="scrypt"
    )
    account_token_issued_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
