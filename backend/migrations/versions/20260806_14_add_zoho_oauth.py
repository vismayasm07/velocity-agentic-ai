"""Add Zoho OAuth state and encrypted connection storage.

Revision ID: 20260806_14
Revises: 20260806_13
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260806_14"
down_revision: str | None = "20260806_13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "zoho_oauth_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash"),
    )
    op.create_index("ix_zoho_oauth_states_state_hash", "zoho_oauth_states", ["state_hash"], unique=True)
    op.create_index("ix_zoho_oauth_states_created_by", "zoho_oauth_states", ["created_by"])
    op.create_index("ix_zoho_oauth_states_expires_at", "zoho_oauth_states", ["expires_at"])
    op.create_table(
        "zoho_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=False),
        sa.Column("api_domain", sa.String(length=255), nullable=False),
        sa.Column("authorized_scopes", sa.Text(), nullable=False),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("connected_by", sa.Uuid(), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["connected_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_zoho_connections_connected_by", "zoho_connections", ["connected_by"])


def downgrade() -> None:
    op.drop_table("zoho_connections")
    op.drop_table("zoho_oauth_states")