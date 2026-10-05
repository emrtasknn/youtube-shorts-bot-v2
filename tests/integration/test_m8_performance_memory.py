from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.application.services.performance_aggregation import PerformanceAggregationService
from app.application.services.performance_baseline import PerformanceBaselineService
from app.application.services.performance_memory import (
    PerformanceMemoryNotFoundError,
    PerformanceMemoryService,
)
from app.domain.enums import (
    AssetStatus,
    AssetType,
    ContentCategory,
    PublicationPlatform,
    PublicationStatus,
    RunType,
    SceneStatus,
    ScriptStatus,
)
from app.infrastructure.database.models import (
    AssetModel,
    AssetUsageModel,
    ContentModel,
    PerformanceProductionSnapshotModel,
    PerformanceSnapshotModel,
    PublicationModel,
    RunModel,
    SceneModel,
    ScriptModel,
)


def database_url() -> str:
    import os

    value = os.getenv("DATABASE_URL")
    if not value:
        pytest.skip("DATABASE_URL is required for the M8 integration test")
    return value


def create_memory_fixture(session: Session) -> PublicationModel:
    content = ContentModel(
        content_key=f"m8-2-{uuid4()}",
        language="en",
        category=ContentCategory.HISTORY_FACT,
        topic="M8.2 linking test",
        angle="A controlled linking path",
    )
    session.add(content)
    session.flush()

    run = RunModel(
        run_key=f"m8-2-{uuid4()}",
        content_id=content.id,
        run_type=RunType.MANUAL,
        language="en",
        strategy="custom_single_vertical_slice",
    )
    session.add(run)
    session.flush()

    published_at = datetime(2026, 10, 4, 19, 0, tzinfo=UTC)
    script = ScriptModel(
        content_id=content.id,
        version=1,
        language="en",
        hook="How did this happen?",
        body="A short test script.",
        duration_target=Decimal("34.00"),
        word_count=92,
        status=ScriptStatus.APPROVED,
        created_at=datetime(2026, 10, 4, 18, 0, tzinfo=UTC),
    )
    session.add(script)
    session.flush()

    scene = SceneModel(
        script_id=script.id,
        scene_index=0,
        duration=Decimal("5.00"),
        narration="Test narration.",
        status=SceneStatus.READY,
    )
    session.add(scene)
    session.flush()

    asset = AssetModel(
        asset_type=AssetType.VIDEO,
        provider="pexels",
        provider_asset_id="asset-1",
        status=AssetStatus.READY,
    )
    session.add(asset)
    session.flush()

    session.add(
        AssetUsageModel(
            asset_id=asset.id,
            scene_id=scene.id,
            run_id=run.id,
            role="PRIMARY",
        )
    )

    publication = PublicationModel(
        run_id=run.id,
        platform=PublicationPlatform.YOUTUBE,
        status=PublicationStatus.PUBLISHED,
        platform_post_id=f"youtube-{uuid4()}",
        published_at=published_at,
    )
    session.add(publication)
    session.flush()

    session.add(
        PerformanceSnapshotModel(
            publication_id=publication.id,
            platform="YOUTUBE",
            platform_post_id=publication.platform_post_id,
            measured_at=published_at,
            views=1000,
        )
    )
    session.flush()
    return publication


def test_performance_memory_links_publication_to_content_and_script() -> None:
    engine = create_engine(database_url())
    try:
        with Session(engine) as session:
            publication = create_memory_fixture(session)

            memory = PerformanceMemoryService(session).get_for_publication(publication.id)

            assert memory.publication_id == publication.id
            assert memory.run_id == publication.run_id
            assert memory.features.category == "HISTORY_FACT"
            assert memory.features.topic == "M8.2 linking test"
            assert memory.features.hook == "How did this happen?"
            assert memory.features.scene_count == 1
            assert memory.features.visual_providers == ("pexels",)
            assert memory.features.production_strategy == "custom_single_vertical_slice"
            session.rollback()
    finally:
        engine.dispose()


def test_performance_memory_requires_performance_snapshot() -> None:
    engine = create_engine(database_url())
    try:
        with Session(engine) as session:
            content = ContentModel(
                content_key=f"m8-2-no-snapshot-{uuid4()}",
                language="en",
                category=ContentCategory.HISTORY_FACT,
                topic="No snapshot",
            )
            session.add(content)
            session.flush()

            run = RunModel(
                run_key=f"m8-2-no-snapshot-{uuid4()}",
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
                platform_post_id="youtube-no-snapshot",
                published_at=datetime(2026, 10, 4, 19, 0, tzinfo=UTC),
            )
            session.add(publication)
            session.flush()

            with pytest.raises(PerformanceMemoryNotFoundError, match="performance snapshot"):
                PerformanceMemoryService(session).get_for_publication(publication.id)
            session.rollback()
    finally:
        engine.dispose()


def test_production_snapshot_can_be_captured_before_metrics_exist() -> None:
    engine = create_engine(database_url())
    try:
        with Session(engine) as session:
            publication = create_memory_fixture(session)
            session.query(PerformanceSnapshotModel).filter(
                PerformanceSnapshotModel.publication_id == publication.id
            ).delete(synchronize_session=False)
            session.flush()

            service = PerformanceMemoryService(session)
            captured = service.capture_production_snapshot(publication.id)

            assert captured.features.topic == "M8.2 linking test"
            assert captured.features.hook == "How did this happen?"
            assert captured.features.visual_providers == ("pexels",)
            assert (
                session.scalar(
                    select(PerformanceProductionSnapshotModel).where(
                        PerformanceProductionSnapshotModel.publication_id == publication.id
                    )
                )
                is not None
            )
            session.rollback()
    finally:
        engine.dispose()


def test_production_snapshot_is_immutable_and_idempotent() -> None:
    engine = create_engine(database_url())
    try:
        with Session(engine) as session:
            publication = create_memory_fixture(session)
            service = PerformanceMemoryService(session)

            memory = service.get_for_publication(publication.id)
            saved = service.save_production_snapshot(memory)

            assert saved.features.topic == "M8.2 linking test"
            snapshot = session.scalar(
                select(PerformanceProductionSnapshotModel).where(
                    PerformanceProductionSnapshotModel.publication_id == publication.id
                )
            )
            assert snapshot is not None
            assert snapshot.visual_providers == ["pexels"]

            content = session.get(ContentModel, memory.content_id)
            assert content is not None
            content.topic = "Changed after publication"

            script = session.get(ScriptModel, memory.script_id)
            assert script is not None
            script.hook = "Changed hook after publication"
            session.flush()

            second = service.save_production_snapshot(service.get_for_publication(publication.id))

            assert second.features.topic == "M8.2 linking test"
            assert second.features.hook == "How did this happen?"
            assert second.features.visual_providers == ("pexels",)
            assert (
                session.scalar(
                    select(func.count(PerformanceProductionSnapshotModel.id)).where(
                        PerformanceProductionSnapshotModel.publication_id == publication.id
                    )
                )
                == 1
            )
            session.rollback()
    finally:
        engine.dispose()


def test_performance_aggregation_groups_by_production_strategy() -> None:
    engine = create_engine(database_url())
    try:
        with Session(engine) as session:
            first = create_memory_fixture(session)
            second = create_memory_fixture(session)

            memory_service = PerformanceMemoryService(session)
            memory_service.capture_production_snapshot(first.id)
            memory_service.capture_production_snapshot(second.id)

            first_snapshot = session.scalar(
                select(PerformanceSnapshotModel).where(
                    PerformanceSnapshotModel.publication_id == first.id
                )
            )
            second_snapshot = session.scalar(
                select(PerformanceSnapshotModel).where(
                    PerformanceSnapshotModel.publication_id == second.id
                )
            )
            assert first_snapshot is not None
            assert second_snapshot is not None

            first_snapshot.views = 1000
            first_snapshot.likes = 50
            first_snapshot.comments = 8
            first_snapshot.shares = 4
            first_snapshot.subscribers_gained = 5
            first_snapshot.average_view_duration_seconds = Decimal("12.00")
            first_snapshot.retention = Decimal("0.40")

            second_snapshot.views = 1400
            second_snapshot.likes = 70
            second_snapshot.comments = 12
            second_snapshot.shares = 6
            second_snapshot.subscribers_gained = 7
            second_snapshot.average_view_duration_seconds = Decimal("14.00")
            second_snapshot.retention = Decimal("0.60")
            session.flush()

            aggregates = PerformanceAggregationService(session).aggregate_by_production_strategy(
                category="HISTORY_FACT",
                language="en",
                platform="YOUTUBE",
            )

            assert len(aggregates) == 1
            aggregate = aggregates[0]
            assert aggregate.sample_count == 2
            assert aggregate.views_total == 2400
            assert aggregate.likes_total == 120
            assert aggregate.comments_total == 20
            assert aggregate.shares_total == 10
            assert aggregate.subscribers_gained_total == 12
            assert aggregate.average_view_duration_seconds == Decimal("13.00")
            assert aggregate.average_retention == Decimal("0.50")
            assert aggregate.production_strategy == "custom_single_vertical_slice"
            session.rollback()
    finally:
        engine.dispose()


def test_performance_baseline_is_derived_from_aggregate_metrics() -> None:
    engine = create_engine(database_url())
    try:
        with Session(engine) as session:
            first = create_memory_fixture(session)
            second = create_memory_fixture(session)

            memory_service = PerformanceMemoryService(session)
            memory_service.capture_production_snapshot(first.id)
            memory_service.capture_production_snapshot(second.id)

            first_snapshot = session.scalar(
                select(PerformanceSnapshotModel).where(
                    PerformanceSnapshotModel.publication_id == first.id
                )
            )
            second_snapshot = session.scalar(
                select(PerformanceSnapshotModel).where(
                    PerformanceSnapshotModel.publication_id == second.id
                )
            )
            assert first_snapshot is not None
            assert second_snapshot is not None

            first_snapshot.views = 1000
            first_snapshot.likes = 50
            first_snapshot.comments = 8
            first_snapshot.shares = 4
            first_snapshot.subscribers_gained = 5
            first_snapshot.average_view_duration_seconds = Decimal("12.00")
            first_snapshot.retention = Decimal("0.40")

            second_snapshot.views = 1400
            second_snapshot.likes = 70
            second_snapshot.comments = 12
            second_snapshot.shares = 6
            second_snapshot.subscribers_gained = 7
            second_snapshot.average_view_duration_seconds = Decimal("14.00")
            second_snapshot.retention = Decimal("0.60")
            session.flush()

            baselines = PerformanceBaselineService(session).build_baseline(
                category="HISTORY_FACT",
                language="en",
                platform="YOUTUBE",
            )

            assert len(baselines) == 1
            baseline = baselines[0]
            assert baseline.sample_count == 2
            assert baseline.average_views == Decimal("1200")
            assert baseline.average_likes == Decimal("60")
            assert baseline.average_comments == Decimal("10")
            assert baseline.average_shares == Decimal("5")
            assert baseline.average_subscribers_gained == Decimal("6")
            assert baseline.engagement_rate == Decimal("150") / Decimal("2400")
            assert baseline.subscriber_conversion_rate == Decimal("12") / Decimal("2400")
            assert baseline.average_view_duration_seconds == Decimal("13.00")
            assert baseline.average_retention == Decimal("0.50")
            assert baseline.production_strategy == "custom_single_vertical_slice"
            session.rollback()
    finally:
        engine.dispose()
