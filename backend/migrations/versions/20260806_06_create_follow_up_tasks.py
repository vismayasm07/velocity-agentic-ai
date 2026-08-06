"""Create follow-up tasks.

Revision ID: 20260806_06
Revises: 20260806_05
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260806_06"
down_revision: str | None = "20260806_05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "follow_up_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("deal_id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("assigned_to", sa.String(length=120), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["bottleneck_incidents.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("incident_id", name="uq_follow_up_task_incident"),
    )
    op.create_index("ix_follow_up_tasks_assigned_to", "follow_up_tasks", ["assigned_to"])
    op.create_index("ix_follow_up_tasks_created_by", "follow_up_tasks", ["created_by"])
    op.create_index("ix_follow_up_tasks_deal_id", "follow_up_tasks", ["deal_id"])
    op.create_index("ix_follow_up_tasks_due_at", "follow_up_tasks", ["due_at"])
    op.create_index("ix_follow_up_tasks_incident_id", "follow_up_tasks", ["incident_id"])
    op.create_index("ix_follow_up_tasks_status", "follow_up_tasks", ["status"])


def downgrade() -> None:
    op.drop_index("ix_follow_up_tasks_status", table_name="follow_up_tasks")
    op.drop_index("ix_follow_up_tasks_incident_id", table_name="follow_up_tasks")
    op.drop_index("ix_follow_up_tasks_due_at", table_name="follow_up_tasks")
    op.drop_index("ix_follow_up_tasks_deal_id", table_name="follow_up_tasks")
    op.drop_index("ix_follow_up_tasks_created_by", table_name="follow_up_tasks")
    op.drop_index("ix_follow_up_tasks_assigned_to", table_name="follow_up_tasks")
    op.drop_table("follow_up_tasks")