"""M14 Telegram update replay protection

Revision ID: 0011_m14_telegram_receipts
Revises: 0010_m13_optimization_decisions
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_m14_telegram_receipts"
down_revision = "0010_m13_optimization_decisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_update_receipts",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("update_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("update_id", name="uq_telegram_update_receipts_update_id"),
    )


def downgrade() -> None:
    op.drop_table("telegram_update_receipts")
