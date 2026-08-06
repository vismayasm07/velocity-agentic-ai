"""Create agent analyses and audit events.

Revision ID: 20260806_05
Revises: 20260805_04
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260806_05"
down_revision: str | None = "20260805_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("root_cause", sa.Text(), nullable=True),
        sa.Column("supporting_evidence", sa.JSON(), nullable=True),
        sa.Column("risk_explanation", sa.Text(), nullable=True),
        sa.Column("recommended_action", sa.Text(), nullable=True),
        sa.Column("action_type", sa.String(length=50), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("approval_required", sa.Boolean(), nullable=True),
        sa.Column("policy_references", sa.JSON(), nullable=True),
        sa.Column("expected_outcome", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["bottleneck_incidents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_analyses_incident_id", "agent_analyses", ["incident_id"])
    op.create_index("ix_agent_analyses_status", "agent_analyses", ["status"])
    op.create_table(
        "agent_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["agent_analyses.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["incident_id"], ["bottleneck_incidents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_audit_events_analysis_id", "agent_audit_events", ["analysis_id"])
    op.create_index("ix_agent_audit_events_event_type", "agent_audit_events", ["event_type"])
    op.create_index("ix_agent_audit_events_incident_id", "agent_audit_events", ["incident_id"])
    op.create_index("ix_agent_audit_events_status", "agent_audit_events", ["status"])


def downgrade() -> None:
    op.drop_index("ix_agent_audit_events_status", table_name="agent_audit_events")
    op.drop_index("ix_agent_audit_events_incident_id", table_name="agent_audit_events")
    op.drop_index("ix_agent_audit_events_event_type", table_name="agent_audit_events")
    op.drop_index("ix_agent_audit_events_analysis_id", table_name="agent_audit_events")
    op.drop_table("agent_audit_events")
    op.drop_index("ix_agent_analyses_status", table_name="agent_analyses")
    op.drop_index("ix_agent_analyses_incident_id", table_name="agent_analyses")
    op.drop_table("agent_analyses")