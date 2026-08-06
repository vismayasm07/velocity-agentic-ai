"""Create bottleneck incidents table.

Revision ID: 20260805_03
Revises: 20260805_02
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260805_03"
down_revision: str | None = "20260805_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bottleneck_incidents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        sa.Column("incident_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "detected_at",
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
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bottleneck_incidents_deal_id",
        "bottleneck_incidents",
        ["deal_id"],
        unique=False,
    )
    op.create_index(
        "ix_bottleneck_incidents_incident_type",
        "bottleneck_incidents",
        ["incident_type"],
        unique=False,
    )
    op.create_index(
        "ix_bottleneck_incidents_severity",
        "bottleneck_incidents",
        ["severity"],
        unique=False,
    )
    op.create_index(
        "ix_bottleneck_incidents_status",
        "bottleneck_incidents",
        ["status"],
        unique=False,
    )
    op.create_index(
        "uq_open_stalled_incident_per_deal",
        "bottleneck_incidents",
        ["deal_id", "incident_type"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_open_stalled_incident_per_deal", table_name="bottleneck_incidents"
    )
    op.drop_index(
        "ix_bottleneck_incidents_status", table_name="bottleneck_incidents"
    )
    op.drop_index(
        "ix_bottleneck_incidents_severity", table_name="bottleneck_incidents"
    )
    op.drop_index(
        "ix_bottleneck_incidents_incident_type", table_name="bottleneck_incidents"
    )
    op.drop_index(
        "ix_bottleneck_incidents_deal_id", table_name="bottleneck_incidents"
    )
    op.drop_table("bottleneck_incidents")