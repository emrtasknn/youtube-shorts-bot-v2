"""M13 optimization decision persistence

Revision ID: 0010_m13_optimization_decisions
Revises: 0009_m12_experimentation
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_m13_optimization_decisions"
down_revision = "0009_m12_experimentation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "optimization_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_version", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("experiment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dimension", sa.String(length=64)),
        sa.Column("winner_variant_id", postgresql.UUID(as_uuid=True)),
        sa.Column("value", sa.String(length=500)),
        sa.Column("control_variant_id", postgresql.UUID(as_uuid=True)),
        sa.Column("uplift", sa.Numeric(8, 4)),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("rationale", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("decision_id", name="uq_optimization_decisions_decision_id"),
        sa.Index(
            "ix_optimization_decisions_experiment_created",
            "experiment_id",
            "created_at",
        ),
    )


def downgrade() -> None:
    op.drop_table("optimization_decisions")
