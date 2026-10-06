"""M14 durable provider idempotency records

Revision ID: 0013_m14_provider_idempotency
Revises: 0012_m14_youtube_upload_state
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_m14_provider_idempotency"
down_revision = "0012_m14_youtube_upload_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_idempotency",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("request_id", sa.String(length=255), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("output", sa.JSON(), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=False),
        sa.Column("cost", sa.Numeric(12, 6), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_provider_idempotency_key"),
    )
    op.create_index(
        "ix_provider_idempotency_expires",
        "provider_idempotency",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_provider_idempotency_expires", table_name="provider_idempotency")
    op.drop_table("provider_idempotency")
