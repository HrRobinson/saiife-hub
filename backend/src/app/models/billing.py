from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class Subscription(Base):
    """The authority on whether this account is entitled to a cloud tenant."""

    __tablename__ = "subscriptions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    stripe_customer_id: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        String(80), unique=True, nullable=True
    )
    # incomplete | active | past_due | canceled
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="incomplete")
    current_period_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class StripeEvent(Base):
    """Webhook idempotency ledger. `event_id` is the PRIMARY KEY: a replayed
    Stripe delivery collides on insert, which is how we detect it."""

    __tablename__ = "stripe_events"
    event_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
