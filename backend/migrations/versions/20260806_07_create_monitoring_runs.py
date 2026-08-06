"""Create proactive monitoring runs.

Revision ID: 20260806_07
Revises: 20260806_06
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260806_07"
down_revision: str | None = "20260806_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "monitoring_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deals_scanned", sa.Integer(), nullable=False),
        sa.Column("incidents_created", sa.Integer(), nullable=False),
        sa.Column("incidents_updated", sa.Integer(), nullable=False),
        sa.Column("errors_encountered", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_monitoring_runs_started_at", "monitoring_runs", ["started_at"])
    op.create_index("ix_monitoring_runs_status", "monitoring_runs", ["status"])
    op.alter_column("agent_audit_events", "incident_id", nullable=True)
    op.add_column("agent_audit_events", sa.Column("monitoring_run_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_agent_audit_events_monitoring_run_id",
        "agent_audit_events",
        "monitoring_runs",
        ["monitoring_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_agent_audit_events_monitoring_run_id",
        "agent_audit_events",
        ["monitoring_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_audit_events_monitoring_run_id", table_name="agent_audit_events")
    op.drop_constraint(
        "fk_agent_audit_events_monitoring_run_id",
        "agent_audit_events",
        type_="foreignkey",
    )
    op.drop_column("agent_audit_events", "monitoring_run_id")
    op.alter_column("agent_audit_events", "incident_id", nullable=False)
    op.drop_index("ix_monitoring_runs_status", table_name="monitoring_runs")
    op.drop_index("ix_monitoring_runs_started_at", table_name="monitoring_runs")
    op.drop_table("monitoring_runs")