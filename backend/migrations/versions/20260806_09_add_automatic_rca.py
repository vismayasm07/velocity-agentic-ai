"""Add automatic RCA settings and durable analysis claims.

Revision ID: 20260806_09
Revises: 20260806_08
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260806_09"
down_revision: str | None = "20260806_08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "monitoring_settings",
        sa.Column(
            "automatic_rca_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "monitoring_settings",
        sa.Column(
            "automatic_rca_min_risk_score",
            sa.Integer(),
            server_default=sa.text("80"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_monitoring_settings_rca_risk_score",
        "monitoring_settings",
        "automatic_rca_min_risk_score BETWEEN 0 AND 100",
    )
    op.add_column(
        "bottleneck_incidents",
        sa.Column(
            "analysis_state",
            sa.String(length=30),
            server_default="PENDING_ANALYSIS",
            nullable=False,
        ),
    )
    op.add_column(
        "bottleneck_incidents",
        sa.Column("analysis_fingerprint", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_bottleneck_incidents_analysis_state",
        "bottleneck_incidents",
        ["analysis_state"],
    )
    op.add_column(
        "agent_analyses",
        sa.Column("trigger", sa.String(length=20), server_default="MANUAL", nullable=False),
    )
    op.add_column(
        "agent_analyses",
        sa.Column("input_fingerprint", sa.String(length=64), nullable=True),
    )
    op.execute(
        "UPDATE agent_analyses SET input_fingerprint = md5(id::text) || md5(incident_id::text)"
    )
    op.alter_column("agent_analyses", "input_fingerprint", nullable=False)
    op.create_index(
        "uq_active_analysis_per_incident",
        "agent_analyses",
        ["incident_id"],
        unique=True,
        postgresql_where=sa.text("status = 'RUNNING'"),
    )


def downgrade() -> None:
    op.drop_index("uq_active_analysis_per_incident", table_name="agent_analyses")
    op.drop_column("agent_analyses", "input_fingerprint")
    op.drop_column("agent_analyses", "trigger")
    op.drop_index(
        "ix_bottleneck_incidents_analysis_state", table_name="bottleneck_incidents"
    )
    op.drop_column("bottleneck_incidents", "analysis_fingerprint")
    op.drop_column("bottleneck_incidents", "analysis_state")
    op.drop_constraint(
        "ck_monitoring_settings_rca_risk_score",
        "monitoring_settings",
        type_="check",
    )
    op.drop_column("monitoring_settings", "automatic_rca_min_risk_score")
    op.drop_column("monitoring_settings", "automatic_rca_enabled")