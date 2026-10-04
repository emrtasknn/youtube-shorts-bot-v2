from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine

from app.application.ports.analytics import VideoPerformance
from app.application.services.metrics_collector import (
    MetricsCollectionRequest,
    MetricsCollector,
)
from app.application.services.performance_snapshot import PerformanceSnapshotService
from app.domain.enums import ContentCategory, PublicationPlatform, PublicationStatus, RunType
from app.infrastructure.database.models import ContentModel, PublicationModel, RunModel
from sqlalchemy.orm import Session


pytestmark = pytest.mark.integration


def database_url() -> str:
    value = os.getenv("DATABASE_URL")
    if not value:
        pytest.skip("DATABASE_URL is required for the M7 integration test")
    return value


class FakeAnalyticsProvider:
    async def fetch_video_performance(
        self,
        *,
        publication_id: str,
        platform_post_id: str,
        measured_at: datetime,
    ) -> VideoPerformance:
        return VideoPerformance(
            publication_id=publication_id,
            platform="YOUTUBE",
            platform_post_id=platform_post_id,
            measured_at=measured_at,
            views=1250,
            likes=84,
            comments=7,
            shares=12,
            subscribers_gained=9,
            watch_time_seconds=1834.5,
            average_view_duration_seconds=42.75,
            retention=0.71,
        )


def create_publication(session: Session) -> PublicationModel:
    content = ContentModel(
        content_key=f"m7-6-{uuid4()}",
        language="en",
        category=ContentCategory.HISTORY_FACT,
        topic="M7.6 integration test",
    )
    session.add(content)
    session.flush()

    run = RunModel(
        run_key=f"m7-6-{uuid4()}",
        content_id=content.id,
        run_type=RunType.MANUAL,
        language="en",
    )
    session.add(run)
    session.flush()

    publication = PublicationModel(
        run_id=run.id,
        platform=PublicationPlatform.YOUTUBE,
        status=PublicationStatus.PUBLISHED,
        platform_post_id=f"youtube-{uuid4()}",
    )
    session.add(publication)
    session.flush()
    return publication


@pytest.mark.asyncio
async def test_metrics_collection_persists_and_is_idempotent() -> None:
    engine = create_engine(database_url())
    try:
        with Session(engine) as session:
            publication = create_publication(session)
            measured_at = datetime(2026, 10, 4, 19, 0, tzinfo=UTC)
            request = MetricsCollectionRequest(
                publication_id=str(publication.id),
                platform_post_id=publication.platform_post_id,
                measured_at=measured_at,
            )
            collector = MetricsCollector(
                FakeAnalyticsProvider(),
                PerformanceSnapshotService(session),
            )

            first = await collector.collect(request)
            second = await collector.collect(request)

            snapshots = PerformanceSnapshotService(session).list_for_publication(
                str(publication.id)
            )

            assert first.views == 1250
            assert second.views == 1250
            assert len(snapshots) == 1
            assert snapshots[0].platform_post_id == publication.platform_post_id
            assert snapshots[0].measured_at == measured_at
            assert snapshots[0].retention == pytest.approx(0.71)
            session.rollback()
    finally:
        engine.dispose()
