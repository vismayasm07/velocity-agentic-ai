"""Add approval-controlled deal owner reassignment.

Revision ID: 20260806_12
Revises: 20260806_11
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260806_12"
down_revision: str | None = "20260806_11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "monitoring_settings",
        sa.Column(
            "high_impact_actions_disabled",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.create_table(
        "sales_owner_capacities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_name", sa.String(length=120), nullable=False),
        sa.Column("active_deals", sa.Integer(), nullable=False),
        sa.Column("max_active_deals", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_name"),
    )
    op.create_index("ix_sales_owner_capacities_owner_name", "sales_owner_capacities", ["owner_name"], unique=True)
    op.create_index("ix_sales_owner_capacities_is_active", "sales_owner_capacities", ["is_active"])
    op.execute(
        sa.text(
            """
            INSERT INTO sales_owner_capacities
                (id, owner_name, active_deals, max_active_deals, is_active)
            VALUES
                ('20000000-0000-4000-8000-000000000001', 'Maya Chen', 18, 18, true),
                ('20000000-0000-4000-8000-000000000002', 'Liam Brooks', 14, 18, true),
                ('20000000-0000-4000-8000-000000000003', 'Ava Patel', 11, 18, true),
                ('20000000-0000-4000-8000-000000000004', 'Noah Garcia', 8, 18, true)
            """
        )
    )
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("agent_analysis_id", sa.Uuid(), nullable=False),
        sa.Column("action_type", sa.String(length=50), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("current_owner", sa.String(length=120), nullable=False),
        sa.Column("proposed_owner", sa.String(length=120), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("expected_outcome", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_analysis_id"], ["agent_analyses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["incident_id"], ["bottleneck_incidents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("incident_id", "agent_analysis_id", "action_type", "requested_by", "proposed_owner", "status", "reviewed_by", "expires_at"):
        op.create_index(f"ix_approval_requests_{column}", "approval_requests", [column])
    op.create_index(
        "uq_pending_reassignment_per_incident",
        "approval_requests",
        ["incident_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING' AND action_type = 'REQUEST_REASSIGNMENT'"),
    )


def downgrade() -> None:
    op.drop_table("approval_requests")
    op.drop_table("sales_owner_capacities")
    op.drop_column("monitoring_settings", "high_impact_actions_disabled")