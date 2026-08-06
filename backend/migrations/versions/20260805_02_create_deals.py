"""Create deals table.

Revision ID: 20260805_02
Revises: 20260805_01
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260805_02"
down_revision: str | None = "20260805_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "deals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("value", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("stage", sa.String(length=50), nullable=False),
        sa.Column("owner_name", sa.String(length=120), nullable=False),
        sa.Column("stage_entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_follow_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_deals_name"), "deals", ["name"], unique=False)
    op.create_index(op.f("ix_deals_owner_name"), "deals", ["owner_name"], unique=False)
    op.create_index(op.f("ix_deals_stage"), "deals", ["stage"], unique=False)
    op.create_index(op.f("ix_deals_status"), "deals", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_deals_status"), table_name="deals")
    op.drop_index(op.f("ix_deals_stage"), table_name="deals")
    op.drop_index(op.f("ix_deals_owner_name"), table_name="deals")
    op.drop_index(op.f("ix_deals_name"), table_name="deals")
    op.drop_table("deals")