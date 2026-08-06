"""Create admin-managed monitoring settings.

Revision ID: 20260806_08
Revises: 20260806_07
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260806_08"
down_revision: str | None = "20260806_07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "monitoring_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("monitoring_enabled", sa.Boolean(), nullable=False),
        sa.Column("scan_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("stage_sla_hours", sa.Integer(), nullable=False),
        sa.Column("inactivity_threshold_hours", sa.Integer(), nullable=False),
        sa.Column("overdue_follow_up_enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_monitoring_settings_updated_by", "monitoring_settings", ["updated_by"]
    )


def downgrade() -> None:
    op.drop_index("ix_monitoring_settings_updated_by", table_name="monitoring_settings")
    op.drop_table("monitoring_settings")