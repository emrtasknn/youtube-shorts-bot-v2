"""Create M9.5 recommendation persistence."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_m9_recommendations"
down_revision = "0005_m8_prod_feature_snapshot"
branch_labels = None
depends_on = None


def uuid_type() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "recommendations",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("recommendation_id", uuid_type(), nullable=False),
        sa.Column("signal_id", uuid_type(), nullable=False),
        sa.Column("feature", sa.String(100), nullable=False),
        sa.Column("feature_value", sa.String(500), nullable=False),
        sa.Column("metric", sa.String(100), nullable=False),
        sa.Column("observed_value", sa.Numeric(18, 6), nullable=False),
        sa.Column("baseline_value", sa.Numeric(18, 6)),
        sa.Column("delta", sa.Numeric(18, 6)),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("baseline_available", sa.Boolean(), nullable=False),
        sa.Column("data_quality_score", sa.Numeric(6, 5), nullable=False),
        sa.Column("notes", postgresql.JSONB(), nullable=False),
        sa.Column("confidence", sa.String(32), nullable=False),
        sa.Column("direction", sa.String(32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "recommendation_id",
            name="uq_recommendations_recommendation_id",
        ),
    )
    op.create_index(
        "ix_recommendations_status_created",
        "recommendations",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_recommendations_feature_metric",
        "recommendations",
        ["feature", "metric"],
    )


def downgrade() -> None:
    op.drop_table("recommendations")
