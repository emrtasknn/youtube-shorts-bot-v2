"""Create the M6.9 historical event memory table."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_m6_event_memory"
down_revision = "0002_m5_telegram"
branch_labels = None
depends_on = None


def js() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def ts() -> sa.DateTime:
    return sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "event_memory",
        sa.Column("event_id", sa.String(100), primary_key=True),
        sa.Column("canonical_title", sa.String(500), nullable=False),
        sa.Column("aliases", js(), nullable=False),
        sa.Column("event_date", sa.String(100)),
        sa.Column("location", sa.String(500)),
        sa.Column("entities", js(), nullable=False),
        sa.Column("event_summary", sa.Text()),
        sa.Column("core_facts", js(), nullable=False),
        sa.Column("claims", js(), nullable=False),
        sa.Column("sources", js(), nullable=False),
        sa.Column("first_video_id", sa.String(255)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", ts(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", ts(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_event_memory_canonical_title", "event_memory", ["canonical_title"])
    op.create_index("ix_event_memory_status", "event_memory", ["status"])


def downgrade() -> None:
    op.drop_table("event_memory")
