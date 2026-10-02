"""Create the M1 domain schema."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_m1_domain"
down_revision = None
branch_labels = None
depends_on = None


def uid() -> postgresql.UUID:
    return postgresql.UUID(as_uuid=True)


def js() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def ts() -> sa.DateTime:
    return sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "contents",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("content_key", sa.String(255), nullable=False),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("topic", sa.String(500), nullable=False),
        sa.Column("angle", sa.String(500)),
        sa.Column("summary", sa.Text()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("novelty_score", sa.Numeric(6, 3)),
        sa.Column("created_at", ts(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", ts(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("content_key", name="uq_contents_content_key"),
    )
    op.create_index("ix_contents_status", "contents", ["status"])

    op.create_table(
        "topic_candidates",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("content_id", uid(), sa.ForeignKey("contents.id", ondelete="SET NULL")),
        sa.Column("source", sa.String(255), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("angle", sa.String(500)),
        sa.Column("relevance_score", sa.Numeric(6, 3)),
        sa.Column("novelty_score", sa.Numeric(6, 3)),
        sa.Column("trend_score", sa.Numeric(6, 3)),
        sa.Column("evergreen_score", sa.Numeric(6, 3)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", ts(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_topic_candidates_status", "topic_candidates", ["status"])
    op.create_index("ix_topic_candidates_source", "topic_candidates", ["source"])

    op.create_table(
        "scripts",
        sa.Column("id", uid(), primary_key=True),
        sa.Column(
            "content_id",
            uid(),
            sa.ForeignKey("contents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("hook", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("cta", sa.Text()),
        sa.Column("duration_target", sa.Numeric(8, 2)),
        sa.Column("word_count", sa.Integer()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", ts(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("content_id", "version", name="uq_scripts_content_version"),
    )

    op.create_table(
        "scenes",
        sa.Column("id", uid(), primary_key=True),
        sa.Column(
            "script_id",
            uid(),
            sa.ForeignKey("scripts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scene_index", sa.Integer(), nullable=False),
        sa.Column("duration", sa.Numeric(8, 2)),
        sa.Column("narration", sa.Text()),
        sa.Column("visual_goal", sa.Text()),
        sa.Column("visual_fact", sa.Text()),
        sa.Column("primary_subject", sa.String(500)),
        sa.Column("action", sa.Text()),
        sa.Column("shot_type", sa.String(100)),
        sa.Column("composition", sa.String(255)),
        sa.Column("era", sa.String(255)),
        sa.Column("location", sa.String(500)),
        sa.Column("must_show", js()),
        sa.Column("must_avoid", js()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.UniqueConstraint("script_id", "scene_index", name="uq_scenes_script_index"),
    )

    op.create_table(
        "assets",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("asset_type", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(100)),
        sa.Column("provider_asset_id", sa.String(255)),
        sa.Column("source_url", sa.Text()),
        sa.Column("local_path", sa.Text()),
        sa.Column("checksum", sa.String(128)),
        sa.Column("mime_type", sa.String(100)),
        sa.Column("width", sa.Integer()),
        sa.Column("height", sa.Integer()),
        sa.Column("duration", sa.Numeric(10, 3)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("metadata", js()),
        sa.Column("created_at", ts(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_assets_type_status", "assets", ["asset_type", "status"])
    op.create_index("ix_assets_checksum", "assets", ["checksum"])

    op.create_table(
        "runs",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("run_key", sa.String(255), nullable=False),
        sa.Column(
            "content_id",
            uid(),
            sa.ForeignKey("contents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("run_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("requested_by", sa.String(255)),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("strategy", sa.String(255)),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("budget_target", sa.Numeric(12, 4)),
        sa.Column("estimated_cost", sa.Numeric(12, 4)),
        sa.Column("actual_cost", sa.Numeric(12, 4)),
        sa.Column("started_at", ts()),
        sa.Column("completed_at", ts()),
        sa.Column("created_at", ts(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", ts(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("run_key", name="uq_runs_run_key"),
    )
    op.create_index("ix_runs_status", "runs", ["status"])

    op.create_table(
        "asset_usages",
        sa.Column("id", uid(), primary_key=True),
        sa.Column(
            "asset_id", uid(), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("scene_id", uid(), sa.ForeignKey("scenes.id", ondelete="CASCADE")),
        sa.Column("run_id", uid(), sa.ForeignKey("runs.id", ondelete="CASCADE")),
        sa.Column("role", sa.String(100), nullable=False),
        sa.Column("created_at", ts(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("asset_id", "scene_id", "run_id", "role", name="uq_asset_usage"),
    )

    op.create_table(
        "stage_executions",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("run_id", uid(), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage", sa.String(40), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(100)),
        sa.Column("started_at", ts()),
        sa.Column("completed_at", ts()),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("input_artifact_id", uid()),
        sa.Column("output_artifact_id", uid()),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text()),
        sa.Column("metadata", js()),
        sa.UniqueConstraint("run_id", "stage", "attempt", name="uq_stage_execution"),
    )
    op.create_index("ix_stage_executions_run_stage", "stage_executions", ["run_id", "stage"])

    op.create_table(
        "approvals",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("run_id", uid(), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("requested_at", ts(), server_default=sa.func.now(), nullable=False),
        sa.Column("responded_at", ts()),
        sa.Column("responded_by", sa.String(255)),
        sa.Column("comment", sa.Text()),
        sa.Column("metadata", js()),
    )
    op.create_index("ix_approvals_run_status", "approvals", ["run_id", "status"])

    op.create_table(
        "publications",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("run_id", uid(), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("platform_post_id", sa.String(255)),
        sa.Column("url", sa.Text()),
        sa.Column("title", sa.String(500)),
        sa.Column("description", sa.Text()),
        sa.Column("playlist_id", sa.String(255)),
        sa.Column("published_at", ts()),
        sa.Column("created_at", ts(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", ts(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("run_id", "platform", name="uq_publications_run_platform"),
    )
    op.create_index("ix_publications_status", "publications", ["status"])

    op.create_table(
        "publication_attempts",
        sa.Column("id", uid(), primary_key=True),
        sa.Column(
            "publication_id",
            uid(),
            sa.ForeignKey("publications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(100)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", ts()),
        sa.Column("completed_at", ts()),
        sa.UniqueConstraint("publication_id", "attempt_number", name="uq_publication_attempt"),
    )

    op.create_table(
        "providers",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("configuration", js()),
        sa.Column("created_at", ts(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", ts(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", name="uq_providers_name"),
    )
    op.create_index("ix_providers_category_enabled", "providers", ["category", "enabled"])

    op.create_table(
        "provider_health",
        sa.Column("id", uid(), primary_key=True),
        sa.Column(
            "provider_id",
            uid(),
            sa.ForeignKey("providers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("last_failure_at", ts()),
        sa.Column("cooldown_until", ts()),
        sa.Column("metadata", js()),
        sa.Column("updated_at", ts(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provider_id", name="uq_provider_health_provider"),
    )

    op.create_table(
        "system_events",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("run_id", uid(), sa.ForeignKey("runs.id", ondelete="SET NULL")),
        sa.Column(
            "stage_id",
            uid(),
            sa.ForeignKey("stage_executions.id", ondelete="SET NULL"),
        ),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(100)),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metadata", js()),
        sa.Column("created_at", ts(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_system_events_run_created", "system_events", ["run_id", "created_at"])
    op.create_index("ix_system_events_severity", "system_events", ["severity"])

    op.create_table(
        "cost_events",
        sa.Column("id", uid(), primary_key=True),
        sa.Column("run_id", uid(), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "stage_id",
            uid(),
            sa.ForeignKey("stage_executions.id", ondelete="SET NULL"),
        ),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("operation", sa.String(100), nullable=False),
        sa.Column("amount", sa.Numeric(12, 6), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("metadata", js()),
        sa.Column("created_at", ts(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_cost_events_run_created", "cost_events", ["run_id", "created_at"])


def downgrade() -> None:
    tables = [
        "cost_events",
        "system_events",
        "provider_health",
        "providers",
        "publication_attempts",
        "publications",
        "approvals",
        "stage_executions",
        "asset_usages",
        "runs",
        "assets",
        "scenes",
        "scripts",
        "topic_candidates",
        "contents",
    ]
    for table in tables:
        op.drop_table(table)
