"""Create the M8.3 immutable production feature snapshot table.

Revision ID: 0005_m8_prod_feature_snapshot
Revises: 0004_m7_performance_snapshots
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_m8_prod_feature_snapshot"
down_revision = "0004_m7_performance_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "performance_production_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("publication_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("script_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("platform_post_id", sa.String(length=255), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("topic", sa.String(length=500), nullable=False),
        sa.Column("angle", sa.String(length=500), nullable=True),
        sa.Column("hook", sa.Text(), nullable=True),
        sa.Column("duration_target_seconds", sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("scene_count", sa.Integer(), nullable=True),
        sa.Column("visual_providers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tts_provider", sa.String(length=100), nullable=True),
        sa.Column("production_strategy", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["publication_id"], ["publications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["content_id"], ["contents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["script_id"], ["scripts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "publication_id",
            name="uq_performance_production_snapshot_publication",
        ),
    )
    op.create_index(
        "ix_performance_production_snapshot_content",
        "performance_production_snapshots",
        ["content_id"],
    )
    op.create_index(
        "ix_performance_production_snapshot_category",
        "performance_production_snapshots",
        ["category"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_performance_production_snapshot_category",
        table_name="performance_production_snapshots",
    )
    op.drop_index(
        "ix_performance_production_snapshot_content",
        table_name="performance_production_snapshots",
    )
    op.drop_table("performance_production_snapshots")
