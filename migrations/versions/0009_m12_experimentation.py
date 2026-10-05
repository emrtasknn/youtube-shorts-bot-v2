"""M12 experimentation tables

Revision ID: 0009_m12_experimentation
Revises: 0008_m11_topic_select_decisions
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0009_m12_experimentation"
down_revision = "0008_m11_topic_select_decisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("experiment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("dimension", sa.String(length=64), nullable=False),
        sa.Column("variants", postgresql.JSONB(), nullable=False),
        sa.Column("minimum_sample_size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("experiment_id", name="uq_experiments_experiment_id"),
        sa.Index("ix_experiments_status_created", "status", "created_at"),
    )
    op.create_table(
        "experiment_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("experiment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("assignment_id", name="uq_experiment_assignments_assignment_id"),
        sa.UniqueConstraint("experiment_id", "run_key", name="uq_experiment_assignments_experiment_run"),
        sa.Index("ix_experiment_assignments_experiment_status", "experiment_id", "status"),
    )
    op.create_table(
        "experiment_outcomes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("experiment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("average_views", sa.Numeric(14, 2), nullable=False),
        sa.Column("average_retention", sa.Numeric(8, 5)),
        sa.Column("engagement_rate", sa.Numeric(8, 5)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("assignment_id", name="uq_experiment_outcomes_assignment_id"),
        sa.Index("ix_experiment_outcomes_experiment", "experiment_id"),
    )


def downgrade() -> None:
    op.drop_table("experiment_outcomes")
    op.drop_table("experiment_assignments")
    op.drop_table("experiments")
