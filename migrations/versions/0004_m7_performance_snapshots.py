"""Create M7.2 performance snapshot persistence."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_m7_performance_snapshots"
down_revision = "0003_m6_event_memory"
branch_labels = None
depends_on = None


def uuid_type() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "performance_snapshots",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("publication_id", uuid_type(), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("platform_post_id", sa.String(255), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("likes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("shares", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("subscribers_gained", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("watch_time_seconds", sa.Numeric(12, 3)),
        sa.Column("average_view_duration_seconds", sa.Numeric(12, 3)),
        sa.Column("retention", sa.Numeric(6, 5)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["publication_id"],
            ["publications.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "publication_id",
            "measured_at",
            name="uq_performance_snapshots_publication_measured",
        ),
    )
    op.create_index(
        "ix_performance_snapshots_publication_measured",
        "performance_snapshots",
        ["publication_id", "measured_at"],
    )


def downgrade() -> None:
    op.drop_table("performance_snapshots")
