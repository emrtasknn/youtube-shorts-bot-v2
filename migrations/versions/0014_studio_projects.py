"""Studio projects and photo pool, so the bot survives restarts

Revision ID: 0014_studio_projects
Revises: 0013_m14_provider_idempotency
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_studio_projects"
down_revision = "0013_m14_provider_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "studio_projects",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_studio_projects_chat_id", "studio_projects", ["chat_id"])
    op.create_table(
        "studio_inbox",
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("chat_id"),
    )


def downgrade() -> None:
    op.drop_table("studio_inbox")
    op.drop_index("ix_studio_projects_chat_id", table_name="studio_projects")
    op.drop_table("studio_projects")
