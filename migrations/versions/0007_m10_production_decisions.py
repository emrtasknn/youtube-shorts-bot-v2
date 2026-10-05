"""Create M10.3 production decision persistence and audit."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_m10_production_decisions"
down_revision = "0006_m9_recommendations"
branch_labels = None
depends_on = None


def uuid_type() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "production_decisions",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("decision_id", uuid_type(), nullable=False),
        sa.Column("policy_version", sa.String(100), nullable=False),
        sa.Column("angle", sa.String(500)),
        sa.Column("duration_target_seconds", sa.Numeric(8, 2)),
        sa.Column("production_strategy", sa.String(255)),
        sa.Column("input_recommendation_ids", postgresql.JSONB(), nullable=False),
        sa.Column("eligible_recommendation_ids", postgresql.JSONB(), nullable=False),
        sa.Column("applied_recommendation_ids", postgresql.JSONB(), nullable=False),
        sa.Column("rejected_recommendation_ids", postgresql.JSONB(), nullable=False),
        sa.Column("rationale", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "decision_id",
            name="uq_production_decisions_decision_id",
        ),
    )
    op.create_index(
        "ix_production_decisions_policy_created",
        "production_decisions",
        ["policy_version", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("production_decisions")
