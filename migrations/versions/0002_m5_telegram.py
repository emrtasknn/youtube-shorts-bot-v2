"""M5 Telegram approval uniqueness.

Revision ID: 0002_m5_telegram
Revises: 0001_m1_domain
"""

from alembic import op

revision = "0002_m5_telegram"
down_revision = "0001_m1_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_approvals_run_id", "approvals", ["run_id"])


def downgrade() -> None:
    op.drop_constraint("uq_approvals_run_id", "approvals", type_="unique")
