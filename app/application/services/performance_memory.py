from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.performance_memory import PerformanceMemory, PerformanceProductionFeatures
from app.infrastructure.database.models import (
    AssetModel,
    AssetUsageModel,
    ContentModel,
    PerformanceSnapshotModel,
    PublicationModel,
    RunModel,
    SceneModel,
    ScriptModel,
)


class PerformanceMemoryNotFoundError(LookupError):
    """Raised when a published performance record cannot be linked to production data."""


class PerformanceMemoryService:
    """Resolves persisted performance into its content and production identity."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_for_publication(self, publication_id: UUID) -> PerformanceMemory:
        publication = self._session.get(PublicationModel, publication_id)
        if publication is None:
            raise PerformanceMemoryNotFoundError("publication not found")
        if not publication.platform_post_id:
            raise PerformanceMemoryNotFoundError("publication has no platform post id")
        if publication.published_at is None:
            raise PerformanceMemoryNotFoundError("publication has no published_at")

        has_snapshot = self._session.scalar(
            select(PerformanceSnapshotModel.id)
            .where(PerformanceSnapshotModel.publication_id == publication_id)
            .limit(1)
        )
        if has_snapshot is None:
            raise PerformanceMemoryNotFoundError("publication has no performance snapshot")

        run = self._session.get(RunModel, publication.run_id)
        if run is None:
            raise PerformanceMemoryNotFoundError("publication run not found")

        content = self._session.get(ContentModel, run.content_id)
        if content is None:
            raise PerformanceMemoryNotFoundError("run content not found")

        script = self._session.scalar(
            select(ScriptModel)
            .where(
                ScriptModel.content_id == content.id,
                ScriptModel.created_at <= publication.published_at,
            )
            .order_by(ScriptModel.version.desc(), ScriptModel.created_at.desc())
            .limit(1)
        )
        if script is None:
            raise PerformanceMemoryNotFoundError("content script not found before publication")

        scene_count = self._session.scalar(
            select(func.count(SceneModel.id)).where(SceneModel.script_id == script.id)
        )

        visual_providers = self._session.scalars(
            select(AssetModel.provider)
            .join(AssetUsageModel, AssetUsageModel.asset_id == AssetModel.id)
            .join(SceneModel, SceneModel.id == AssetUsageModel.scene_id)
            .where(
                AssetUsageModel.run_id == run.id,
                SceneModel.script_id == script.id,
                AssetModel.provider.is_not(None),
            )
            .distinct()
        ).all()

        features = PerformanceProductionFeatures(
            category=str(content.category),
            language=content.language,
            topic=content.topic,
            angle=content.angle,
            hook=script.hook,
            duration_target_seconds=script.duration_target,
            word_count=script.word_count,
            scene_count=int(scene_count or 0),
            visual_providers=visual_providers,
            production_strategy=run.strategy,
        )

        return PerformanceMemory(
            publication_id=publication.id,
            run_id=run.id,
            content_id=content.id,
            script_id=script.id,
            platform=str(publication.platform),
            platform_post_id=publication.platform_post_id,
            published_at=publication.published_at,
            features=features,
        )
