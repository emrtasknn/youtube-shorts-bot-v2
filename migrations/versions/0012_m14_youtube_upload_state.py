"""M14 durable YouTube resumable upload state

Revision ID: 0012_m14_youtube_upload_state
Revises: 0011_m14_telegram_receipts
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_m14_youtube_upload_state"
down_revision = "0011_m14_telegram_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "publication_attempts",
        sa.Column("upload_session_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "publication_attempts",
        sa.Column("bytes_uploaded", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "publication_attempts",
        sa.Column("total_bytes", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("publication_attempts", "total_bytes")
    op.drop_column("publication_attempts", "bytes_uploaded")
    op.drop_column("publication_attempts", "upload_session_url")
