"""Add Zoho synchronization metadata to deals.

Revision ID: 20260806_15
Revises: 20260806_14
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260806_15"
down_revision: str | None = "20260806_14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("deals", sa.Column("zoho_record_id", sa.String(length=100), nullable=True))
    op.add_column(
        "deals",
        sa.Column("source", sa.String(length=20), server_default="local", nullable=False),
    )
    op.add_column(
        "deals", sa.Column("zoho_modified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "deals", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_unique_constraint("uq_deals_zoho_record_id", "deals", ["zoho_record_id"])


def downgrade() -> None:
    op.drop_constraint("uq_deals_zoho_record_id", "deals", type_="unique")
    op.drop_column("deals", "last_synced_at")
    op.drop_column("deals", "zoho_modified_at")
    op.drop_column("deals", "source")
    op.drop_column("deals", "zoho_record_id")