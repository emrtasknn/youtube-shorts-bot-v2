from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.application.services.performance_baseline import PerformanceBaselineService
from app.application.services.performance_memory import PerformanceMemoryService
from app.application.services.performance_time_series import PerformanceTimeSeriesService
from app.domain.performance_memory import PerformanceBaseline, PerformanceQueryResult


class PerformanceQueryNotFoundError(LookupError):
    """Raised when the published performance memory cannot be assembled."""


class PerformanceQueryService:
    """Expose deterministic performance memory through one application contract."""

    def __init__(self, session: Session) -> None:
        self._memory = PerformanceMemoryService(session)
        self._baseline = PerformanceBaselineService(session)
        self._time_series = PerformanceTimeSeriesService(session)

    def get_for_publication(self, publication_id: UUID) -> PerformanceQueryResult:
        memory = self._memory.get_for_publication(publication_id)
        time_series = tuple(self._time_series.get_for_publication(publication_id))

        baselines = self._baseline.build_baseline(
            category=memory.features.category,
            language=memory.features.language,
            platform=memory.platform,
        )
        baseline = self._find_matching_baseline(
            baselines,
            memory.features.production_strategy,
        )

        return PerformanceQueryResult(
            memory=memory,
            baseline=baseline,
            time_series=time_series,
        )

    @staticmethod
    def _find_matching_baseline(
        baselines: tuple[PerformanceBaseline, ...] | list[PerformanceBaseline],
        production_strategy: str | None,
    ) -> PerformanceBaseline | None:
        for baseline in baselines:
            if baseline.production_strategy == production_strategy:
                return baseline
        return None
