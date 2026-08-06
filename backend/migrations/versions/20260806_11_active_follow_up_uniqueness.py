"""Limit follow-up uniqueness to active tasks.

Revision ID: 20260806_11
Revises: 20260806_10
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260806_11"
down_revision: str | None = "20260806_10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_follow_up_task_incident", "follow_up_tasks", type_="unique")
    op.create_index(
        "uq_follow_up_task_active_incident",
        "follow_up_tasks",
        ["incident_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('PENDING', 'IN_PROGRESS')"),
    )


def downgrade() -> None:
    duplicate_incident = op.get_bind().execute(
        sa.text(
            """
            SELECT incident_id
            FROM follow_up_tasks
            GROUP BY incident_id
            HAVING count(*) > 1
            LIMIT 1
            """
        )
    ).scalar_one_or_none()
    if duplicate_incident is not None:
        raise RuntimeError(
            "Cannot restore permanent incident uniqueness while task history contains duplicates"
        )
    op.drop_index("uq_follow_up_task_active_incident", table_name="follow_up_tasks")
    op.create_unique_constraint(
        "uq_follow_up_task_incident", "follow_up_tasks", ["incident_id"]
    )