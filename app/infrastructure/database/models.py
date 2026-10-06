from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import (
    ApprovalStatus,
    AssetStatus,
    AssetType,
    ContentCategory,
    ContentStatus,
    EventSeverity,
    ProviderCategory,
    ProviderHealthStatus,
    PublicationPlatform,
    PublicationStatus,
    RunStatus,
    RunType,
    SceneStatus,
    ScriptStatus,
    Stage,
    StageStatus,
    TopicStatus,
)
from app.infrastructure.database.base import Base


def uuid_pk() -> Mapped[UUID]:
    return mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)


def created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def updated_at() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ContentModel(Base):
    __tablename__ = "contents"
    __table_args__ = (
        UniqueConstraint("content_key", name="uq_contents_content_key"),
        Index("ix_contents_status", "status"),
    )
    id: Mapped[UUID] = uuid_pk()
    content_key: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[ContentCategory] = mapped_column(String(32), nullable=False)
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    angle: Mapped[str | None] = mapped_column(String(500))
    summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ContentStatus] = mapped_column(
        String(32), default=ContentStatus.DRAFT, nullable=False
    )
    novelty_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


class TopicCandidateModel(Base):
    __tablename__ = "topic_candidates"
    __table_args__ = (
        Index("ix_topic_candidates_status", "status"),
        Index("ix_topic_candidates_source", "source"),
    )
    id: Mapped[UUID] = uuid_pk()
    content_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("contents.id", ondelete="SET NULL")
    )
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    angle: Mapped[str | None] = mapped_column(String(500))
    relevance_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    novelty_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    trend_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    evergreen_score: Mapped[Decimal | None] = mapped_column(Numeric(6, 3))
    status: Mapped[TopicStatus] = mapped_column(String(32), default=TopicStatus.NEW, nullable=False)
    created_at: Mapped[datetime] = created_at()


class ScriptModel(Base):
    __tablename__ = "scripts"
    __table_args__ = (UniqueConstraint("content_id", "version", name="uq_scripts_content_version"),)
    id: Mapped[UUID] = uuid_pk()
    content_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("contents.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    hook: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    cta: Mapped[str | None] = mapped_column(Text)
    duration_target: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    word_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[ScriptStatus] = mapped_column(
        String(32), default=ScriptStatus.DRAFT, nullable=False
    )
    created_at: Mapped[datetime] = created_at()


class SceneModel(Base):
    __tablename__ = "scenes"
    __table_args__ = (UniqueConstraint("script_id", "scene_index", name="uq_scenes_script_index"),)
    id: Mapped[UUID] = uuid_pk()
    script_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("scripts.id", ondelete="CASCADE"), nullable=False
    )
    scene_index: Mapped[int] = mapped_column(Integer, nullable=False)
    duration: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    narration: Mapped[str | None] = mapped_column(Text)
    visual_goal: Mapped[str | None] = mapped_column(Text)
    visual_fact: Mapped[str | None] = mapped_column(Text)
    primary_subject: Mapped[str | None] = mapped_column(String(500))
    action: Mapped[str | None] = mapped_column(Text)
    shot_type: Mapped[str | None] = mapped_column(String(100))
    composition: Mapped[str | None] = mapped_column(String(255))
    era: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(500))
    must_show: Mapped[list[Any] | None] = mapped_column(JSONB)
    must_avoid: Mapped[list[Any] | None] = mapped_column(JSONB)
    status: Mapped[SceneStatus] = mapped_column(
        String(32), default=SceneStatus.PLANNED, nullable=False
    )


class AssetModel(Base):
    __tablename__ = "assets"
    __table_args__ = (
        Index("ix_assets_type_status", "asset_type", "status"),
        Index("ix_assets_checksum", "checksum"),
    )
    id: Mapped[UUID] = uuid_pk()
    asset_type: Mapped[AssetType] = mapped_column(String(32), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(100))
    provider_asset_id: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(Text)
    local_path: Mapped[str | None] = mapped_column(Text)
    checksum: Mapped[str | None] = mapped_column(String(128))
    mime_type: Mapped[str | None] = mapped_column(String(100))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    status: Mapped[AssetStatus] = mapped_column(
        String(32), default=AssetStatus.PLANNED, nullable=False
    )
    asset_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = created_at()


class AssetUsageModel(Base):
    __tablename__ = "asset_usages"
    __table_args__ = (
        UniqueConstraint("asset_id", "scene_id", "run_id", "role", name="uq_asset_usage"),
    )
    id: Mapped[UUID] = uuid_pk()
    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    scene_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("scenes.id", ondelete="CASCADE")
    )
    run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = created_at()


class RunModel(Base):
    __tablename__ = "runs"
    __table_args__ = (
        UniqueConstraint("run_key", name="uq_runs_run_key"),
        Index("ix_runs_status", "status"),
    )
    id: Mapped[UUID] = uuid_pk()
    run_key: Mapped[str] = mapped_column(String(255), nullable=False)
    content_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("contents.id", ondelete="CASCADE"), nullable=False
    )
    run_type: Mapped[RunType] = mapped_column(String(32), nullable=False)
    status: Mapped[RunStatus] = mapped_column(String(40), default=RunStatus.CREATED, nullable=False)
    requested_by: Mapped[str | None] = mapped_column(String(255))
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    strategy: Mapped[str | None] = mapped_column(String(255))
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    budget_target: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    actual_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


class StageExecutionModel(Base):
    __tablename__ = "stage_executions"
    __table_args__ = (
        UniqueConstraint("run_id", "stage", "attempt", name="uq_stage_execution"),
        Index("ix_stage_executions_run_stage", "run_id", "stage"),
    )
    id: Mapped[UUID] = uuid_pk()
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[Stage] = mapped_column(String(40), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[StageStatus] = mapped_column(
        String(32), default=StageStatus.PENDING, nullable=False
    )
    provider: Mapped[str | None] = mapped_column(String(100))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    input_artifact_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    output_artifact_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    stage_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)


class ApprovalModel(Base):
    __tablename__ = "approvals"
    __table_args__ = (Index("ix_approvals_run_status", "run_id", "status"),)
    id: Mapped[UUID] = uuid_pk()
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        String(32), default=ApprovalStatus.PENDING, nullable=False
    )
    requested_at: Mapped[datetime] = created_at()
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responded_by: Mapped[str | None] = mapped_column(String(255))
    comment: Mapped[str | None] = mapped_column(Text)
    approval_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)


class PublicationModel(Base):
    __tablename__ = "publications"
    __table_args__ = (
        UniqueConstraint("run_id", "platform", name="uq_publications_run_platform"),
        Index("ix_publications_status", "status"),
    )
    id: Mapped[UUID] = uuid_pk()
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[PublicationPlatform] = mapped_column(String(32), nullable=False)
    status: Mapped[PublicationStatus] = mapped_column(
        String(32), default=PublicationStatus.PENDING, nullable=False
    )
    platform_post_id: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    playlist_id: Mapped[str | None] = mapped_column(String(255))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


class PerformanceProductionSnapshotModel(Base):
    __tablename__ = "performance_production_snapshots"
    __table_args__ = (
        UniqueConstraint("publication_id", name="uq_performance_production_snapshot_publication"),
        Index("ix_performance_production_snapshot_content", "content_id"),
        Index("ix_performance_production_snapshot_category", "category"),
    )
    id: Mapped[UUID] = uuid_pk()
    publication_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("publications.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    content_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("contents.id", ondelete="CASCADE"), nullable=False
    )
    script_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("scripts.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_post_id: Mapped[str] = mapped_column(String(255), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    angle: Mapped[str | None] = mapped_column(String(500))
    hook: Mapped[str | None] = mapped_column(Text)
    duration_target_seconds: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    word_count: Mapped[int | None] = mapped_column(Integer)
    scene_count: Mapped[int | None] = mapped_column(Integer)
    visual_providers: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    tts_provider: Mapped[str | None] = mapped_column(String(100))
    production_strategy: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = created_at()


class PerformanceSnapshotModel(Base):
    __tablename__ = "performance_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "publication_id",
            "measured_at",
            name="uq_performance_snapshots_publication_measured",
        ),
        Index("ix_performance_snapshots_publication_measured", "publication_id", "measured_at"),
    )
    id: Mapped[UUID] = uuid_pk()
    publication_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("publications.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_post_id: Mapped[str] = mapped_column(String(255), nullable=False)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    likes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    shares: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    subscribers_gained: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    watch_time_seconds: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    average_view_duration_seconds: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    retention: Mapped[Decimal | None] = mapped_column(Numeric(6, 5))
    created_at: Mapped[datetime] = created_at()


class RecommendationModel(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint("recommendation_id", name="uq_recommendations_recommendation_id"),
        Index("ix_recommendations_status_created", "status", "created_at"),
        Index("ix_recommendations_feature_metric", "feature", "metric"),
    )
    id: Mapped[UUID] = uuid_pk()
    recommendation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    signal_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    feature: Mapped[str] = mapped_column(String(100), nullable=False)
    feature_value: Mapped[str] = mapped_column(String(500), nullable=False)
    metric: Mapped[str] = mapped_column(String(100), nullable=False)
    observed_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    baseline_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    delta: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    data_quality_score: Mapped[Decimal] = mapped_column(Numeric(6, 5), nullable=False)
    notes: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = created_at()


class PublicationAttemptModel(Base):
    __tablename__ = "publication_attempts"
    __table_args__ = (
        UniqueConstraint("publication_id", "attempt_number", name="uq_publication_attempt"),
    )
    id: Mapped[UUID] = uuid_pk()
    publication_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("publications.id", ondelete="CASCADE"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[PublicationStatus] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    upload_session_url: Mapped[str | None] = mapped_column(Text)
    bytes_uploaded: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    total_bytes: Mapped[int | None] = mapped_column(BigInteger)


class ProviderModel(Base):
    __tablename__ = "providers"
    __table_args__ = (
        UniqueConstraint("name", name="uq_providers_name"),
        Index("ix_providers_category_enabled", "category", "enabled"),
    )
    id: Mapped[UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[ProviderCategory] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    configuration: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


class ProviderHealthModel(Base):
    __tablename__ = "provider_health"
    __table_args__ = (UniqueConstraint("provider_id", name="uq_provider_health_provider"),)
    id: Mapped[UUID] = uuid_pk()
    provider_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("providers.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ProviderHealthStatus] = mapped_column(
        String(32), default=ProviderHealthStatus.HEALTHY, nullable=False
    )
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    updated_at: Mapped[datetime] = updated_at()


class TelegramUpdateReceiptModel(Base):
    __tablename__ = "telegram_update_receipts"
    id: Mapped[UUID] = uuid_pk()
    update_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    created_at: Mapped[datetime] = created_at()


class SystemEventModel(Base):
    __tablename__ = "system_events"
    __table_args__ = (
        Index("ix_system_events_run_created", "run_id", "created_at"),
        Index("ix_system_events_severity", "severity"),
    )
    id: Mapped[UUID] = uuid_pk()
    run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("runs.id", ondelete="SET NULL")
    )
    stage_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("stage_executions.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[EventSeverity] = mapped_column(String(32), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = created_at()


class CostEventModel(Base):
    __tablename__ = "cost_events"
    __table_args__ = (Index("ix_cost_events_run_created", "run_id", "created_at"),)
    id: Mapped[UUID] = uuid_pk()
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
    )
    stage_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("stage_executions.id", ondelete="SET NULL")
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)
    cost_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = created_at()


class EventMemoryModel(Base):
    __tablename__ = "event_memory"
    __table_args__ = (
        Index("ix_event_memory_canonical_title", "canonical_title"),
        Index("ix_event_memory_status", "status"),
    )
    event_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    canonical_title: Mapped[str] = mapped_column(String(500), nullable=False)
    aliases: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    event_date: Mapped[str | None] = mapped_column(String(100))
    location: Mapped[str | None] = mapped_column(String(500))
    entities: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    event_summary: Mapped[str | None] = mapped_column(Text)
    core_facts: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    claims: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    sources: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    first_video_id: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()


class TopicSelectionDecisionModel(Base):
    __tablename__ = "topic_selection_decisions"
    __table_args__ = (
        UniqueConstraint("decision_id", name="uq_topic_selection_decisions_decision_id"),
        Index("ix_topic_selection_decisions_status_created", "status", "created_at"),
    )
    id: Mapped[UUID] = uuid_pk()
    decision_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    selected_candidate_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    selected_topic: Mapped[str | None] = mapped_column(String(500))
    candidate_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    selected_score: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    rationale: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = created_at()


class ExperimentModel(Base):
    __tablename__ = "experiments"
    __table_args__ = (
        UniqueConstraint("experiment_id", name="uq_experiments_experiment_id"),
        Index("ix_experiments_status_created", "status", "created_at"),
    )
    id: Mapped[UUID] = uuid_pk()
    experiment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    dimension: Mapped[str] = mapped_column(String(64), nullable=False)
    variants: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    minimum_sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = created_at()


class ExperimentAssignmentModel(Base):
    __tablename__ = "experiment_assignments"
    __table_args__ = (
        UniqueConstraint("assignment_id", name="uq_experiment_assignments_assignment_id"),
        UniqueConstraint(
            "experiment_id", "run_key", name="uq_experiment_assignments_experiment_run"
        ),
        Index("ix_experiment_assignments_experiment_status", "experiment_id", "status"),
    )
    id: Mapped[UUID] = uuid_pk()
    assignment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    experiment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    variant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    run_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = created_at()


class ExperimentOutcomeModel(Base):
    __tablename__ = "experiment_outcomes"
    __table_args__ = (
        UniqueConstraint("assignment_id", name="uq_experiment_outcomes_assignment_id"),
        Index("ix_experiment_outcomes_experiment", "experiment_id"),
    )
    id: Mapped[UUID] = uuid_pk()
    assignment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    experiment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    variant_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    average_views: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    average_retention: Mapped[Decimal | None] = mapped_column(Numeric(8, 5))
    engagement_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 5))
    created_at: Mapped[datetime] = created_at()


class OptimizationDecisionModel(Base):
    __tablename__ = "optimization_decisions"
    __table_args__ = (
        UniqueConstraint("decision_id", name="uq_optimization_decisions_decision_id"),
        Index("ix_optimization_decisions_experiment_created", "experiment_id", "created_at"),
    )
    id: Mapped[UUID] = uuid_pk()
    decision_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    experiment_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    dimension: Mapped[str | None] = mapped_column(String(64))
    winner_variant_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    value: Mapped[str | None] = mapped_column(String(500))
    control_variant_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    uplift: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = created_at()
