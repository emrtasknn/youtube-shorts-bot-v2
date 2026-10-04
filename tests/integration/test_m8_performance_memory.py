from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

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
