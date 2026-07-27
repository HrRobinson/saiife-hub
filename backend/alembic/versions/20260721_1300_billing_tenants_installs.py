"""billing, tenants and installs

Revision ID: 20260721_1300_billing_tenants_installs
Revises: 20260721_1200_initial_auth
Create Date: 2026-07-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260721_1300_billing_tenants_installs"
down_revision = "20260721_1200_initial_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("stripe_customer_id", sa.String(length=80), nullable=False, unique=True),
        sa.Column("stripe_subscription_id", sa.String(length=80), nullable=True, unique=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "stripe_events",
        sa.Column("event_id", sa.String(length=80), primary_key=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("subscription_id", sa.Uuid(as_uuid=True), sa.ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("cloud_tenant_id", sa.String(length=80), nullable=False, unique=True),
        sa.Column("tenant_lookup_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("account_token_hash", sa.Text(), nullable=False),
        sa.Column("account_token_hash_algo", sa.String(length=20), nullable=False),
        sa.Column("account_token_issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "installs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("installs")
    op.drop_table("tenants")
    op.drop_table("stripe_events")
    op.drop_table("subscriptions")
