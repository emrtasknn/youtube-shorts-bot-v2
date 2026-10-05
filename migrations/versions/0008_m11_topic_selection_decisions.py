"""Create M11.4 topic selection decision persistence and audit."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_m11_topic_select_decisions"
down_revision = "0007_m10_production_decisions"
branch_labels = None
depends_on = None


def uuid_type() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "topic_selection_decisions",
        sa.Column("id", uuid_type(), nullable=False),
        sa.Column("decision_id", uuid_type(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("selected_candidate_id", uuid_type()),
        sa.Column("selected_topic", sa.String(500)),
        sa.Column("candidate_ids", postgresql.JSONB(), nullable=False),
        sa.Column("selected_score", postgresql.JSONB()),
        sa.Column("rationale", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "decision_id",
            name="uq_topic_selection_decisions_decision_id",
        ),
    )
    op.create_index(
        "ix_topic_selection_decisions_status_created",
        "topic_selection_decisions",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("topic_selection_decisions")
