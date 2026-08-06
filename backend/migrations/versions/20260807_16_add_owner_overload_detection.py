"""Add owner overload detection subjects and settings.

Revision ID: 20260807_16
Revises: 20260806_15
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260807_16"
down_revision: str | None = "20260806_15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bottleneck_incidents",
        sa.Column("owner_capacity_id", sa.Uuid(), nullable=True),
    )
    op.alter_column("bottleneck_incidents", "deal_id", nullable=True)
    op.create_foreign_key(
        "fk_incidents_owner_capacity",
        "bottleneck_incidents",
        "sales_owner_capacities",
        ["owner_capacity_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_bottleneck_incidents_owner_capacity_id",
        "bottleneck_incidents",
        ["owner_capacity_id"],
    )
    op.drop_index("uq_open_stalled_incident_per_deal", table_name="bottleneck_incidents")
    op.create_index(
        "uq_open_stalled_incident_per_deal",
        "bottleneck_incidents",
        ["deal_id", "incident_type"],
        unique=True,
        postgresql_where=sa.text("status = 'open' AND deal_id IS NOT NULL"),
    )
    op.create_index(
        "uq_open_owner_incident",
        "bottleneck_incidents",
        ["owner_capacity_id", "incident_type"],
        unique=True,
        postgresql_where=sa.text("status = 'open' AND owner_capacity_id IS NOT NULL"),
    )
    op.create_check_constraint(
        "ck_incident_exactly_one_subject",
        "bottleneck_incidents",
        "num_nonnulls(deal_id, owner_capacity_id) = 1",
    )

    settings = (
        ("owner_overload_enabled", sa.Boolean(), sa.true()),
        ("owner_max_active_deals", sa.Integer(), sa.text("18")),
        ("owner_max_high_risk_deals", sa.Integer(), sa.text("5")),
        ("owner_max_overdue_follow_ups", sa.Integer(), sa.text("5")),
    )
    for name, column_type, default in settings:
        op.add_column(
            "monitoring_settings",
            sa.Column(name, column_type, server_default=default, nullable=False),
        )
    op.add_column(
        "monitoring_settings",
        sa.Column("owner_max_pipeline_value", sa.Numeric(16, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("monitoring_settings", "owner_max_pipeline_value")
    op.drop_column("monitoring_settings", "owner_max_overdue_follow_ups")
    op.drop_column("monitoring_settings", "owner_max_high_risk_deals")
    op.drop_column("monitoring_settings", "owner_max_active_deals")
    op.drop_column("monitoring_settings", "owner_overload_enabled")
    op.drop_constraint(
        "ck_incident_exactly_one_subject", "bottleneck_incidents", type_="check"
    )
    op.drop_index("uq_open_owner_incident", table_name="bottleneck_incidents")
    op.drop_index("uq_open_stalled_incident_per_deal", table_name="bottleneck_incidents")
    op.create_index(
        "uq_open_stalled_incident_per_deal",
        "bottleneck_incidents",
        ["deal_id", "incident_type"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.drop_index(
        "ix_bottleneck_incidents_owner_capacity_id",
        table_name="bottleneck_incidents",
    )
    op.drop_constraint(
        "fk_incidents_owner_capacity", "bottleneck_incidents", type_="foreignkey"
    )
    op.drop_column("bottleneck_incidents", "owner_capacity_id")
    op.alter_column("bottleneck_incidents", "deal_id", nullable=False)