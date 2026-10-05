from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database.base import Base


class ProductionDecisionModel(Base):
    __tablename__ = "production_decisions"
    __table_args__ = (
        UniqueConstraint("decision_id", name="uq_production_decisions_decision_id"),
        Index("ix_production_decisions_policy_created", "policy_version", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    decision_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(100), nullable=False)
    angle: Mapped[str | None] = mapped_column(String(500))
    duration_target_seconds: Mapped[str | None] = mapped_column(String(32))
    production_strategy: Mapped[str | None] = mapped_column(String(255))
    input_recommendation_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    eligible_recommendation_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    applied_recommendation_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    rejected_recommendation_ids: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    rationale: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
