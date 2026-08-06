"""Add safe follow-up action automation.

Revision ID: 20260806_10
Revises: 20260806_09
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260806_10"
down_revision: str | None = "20260806_09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "monitoring_settings",
        sa.Column(
            "automatic_safe_actions_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "monitoring_settings",
        sa.Column(
            "follow_up_due_hours",
            sa.Integer(),
            server_default=sa.text("24"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_monitoring_settings_follow_up_due_hours",
        "monitoring_settings",
        "follow_up_due_hours BETWEEN 1 AND 720",
    )

    op.add_column("follow_up_tasks", sa.Column("agent_analysis_id", sa.Uuid(), nullable=True))
    op.add_column(
        "follow_up_tasks",
        sa.Column("execution_source", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "follow_up_tasks",
        sa.Column("execution_result", sa.JSON(), nullable=True),
    )
    op.add_column(
        "follow_up_tasks",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_follow_up_tasks_agent_analysis_id",
        "follow_up_tasks",
        "agent_analyses",
        ["agent_analysis_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_follow_up_tasks_agent_analysis_id",
        "follow_up_tasks",
        ["agent_analysis_id"],
    )
    op.create_index(
        "ix_follow_up_tasks_execution_source",
        "follow_up_tasks",
        ["execution_source"],
    )
    op.alter_column("follow_up_tasks", "created_by", existing_type=sa.Uuid(), nullable=True)

    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE follow_up_tasks AS task
            SET agent_analysis_id = (
                    SELECT analysis.id
                    FROM agent_analyses AS analysis
                    WHERE analysis.incident_id = task.incident_id
                      AND analysis.status = 'COMPLETED'
                    ORDER BY analysis.created_at DESC
                    LIMIT 1
                ),
                execution_source = 'MANUAL',
                execution_result = json_build_object(
                    'status', 'CREATED',
                    'task_id', task.id::text
                )
            """
        )
    )
    remaining = connection.execute(
        sa.text("SELECT count(*) FROM follow_up_tasks WHERE agent_analysis_id IS NULL")
    ).scalar_one()
    if remaining:
        raise RuntimeError("Cannot migrate follow-up tasks without a completed analysis")
    op.alter_column("follow_up_tasks", "agent_analysis_id", existing_type=sa.Uuid(), nullable=False)
    op.alter_column(
        "follow_up_tasks",
        "execution_source",
        existing_type=sa.String(length=20),
        nullable=False,
    )
    op.alter_column("follow_up_tasks", "execution_result", existing_type=sa.JSON(), nullable=False)


def downgrade() -> None:
    op.alter_column("follow_up_tasks", "created_by", existing_type=sa.Uuid(), nullable=False)
    op.drop_index("ix_follow_up_tasks_execution_source", table_name="follow_up_tasks")
    op.drop_index("ix_follow_up_tasks_agent_analysis_id", table_name="follow_up_tasks")
    op.drop_constraint(
        "fk_follow_up_tasks_agent_analysis_id", "follow_up_tasks", type_="foreignkey"
    )
    op.drop_column("follow_up_tasks", "completed_at")
    op.drop_column("follow_up_tasks", "execution_result")
    op.drop_column("follow_up_tasks", "execution_source")
    op.drop_column("follow_up_tasks", "agent_analysis_id")
    op.drop_constraint(
        "ck_monitoring_settings_follow_up_due_hours",
        "monitoring_settings",
        type_="check",
    )
    op.drop_column("monitoring_settings", "follow_up_due_hours")
    op.drop_column("monitoring_settings", "automatic_safe_actions_enabled")