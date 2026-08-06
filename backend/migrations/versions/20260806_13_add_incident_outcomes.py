"""Add deterministic incident outcome verification.

Revision ID: 20260806_13
Revises: 20260806_12
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260806_13"
down_revision: str | None = "20260806_12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "monitoring_settings",
        sa.Column("outcome_verification_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "monitoring_settings",
        sa.Column("outcome_check_delay_minutes", sa.Integer(), server_default="60", nullable=False),
    )
    op.add_column(
        "monitoring_settings",
        sa.Column("maximum_outcome_checks", sa.Integer(), server_default="3", nullable=False),
    )
    op.add_column(
        "monitoring_settings",
        sa.Column("resolution_risk_threshold", sa.Integer(), server_default="20", nullable=False),
    )
    op.create_table(
        "incident_outcomes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("action_type", sa.String(length=50), nullable=False),
        sa.Column("action_id", sa.Uuid(), nullable=False),
        sa.Column("verification_status", sa.String(length=20), nullable=False),
        sa.Column("previous_risk_score", sa.Integer(), nullable=False),
        sa.Column("current_risk_score", sa.Integer(), nullable=True),
        sa.Column("verification_evidence", sa.JSON(), nullable=False),
        sa.Column("outcome", sa.String(length=30), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["bottleneck_incidents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("incident_id", "action_type", "action_id", "verification_status", "outcome", "next_check_at"):
        op.create_index(f"ix_incident_outcomes_{column}", "incident_outcomes", [column])
    op.create_index(
        "uq_active_outcome_check_per_incident",
        "incident_outcomes",
        ["incident_id"],
        unique=True,
        postgresql_where=sa.text("verification_status IN ('PENDING', 'RUNNING')"),
    )


def downgrade() -> None:
    op.drop_table("incident_outcomes")
    op.drop_column("monitoring_settings", "resolution_risk_threshold")
    op.drop_column("monitoring_settings", "maximum_outcome_checks")
    op.drop_column("monitoring_settings", "outcome_check_delay_minutes")
    op.drop_column("monitoring_settings", "outcome_verification_enabled")