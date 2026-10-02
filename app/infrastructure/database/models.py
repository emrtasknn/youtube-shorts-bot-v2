from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
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
