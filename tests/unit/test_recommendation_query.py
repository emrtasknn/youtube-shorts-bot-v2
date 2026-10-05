from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.application.services.recommendation_query import RecommendationQueryService
from app.domain.learning import (
    ConfidenceLevel,
    LearningEvidence,
    LearningSignal,
    Recommendation,
    RecommendationStatus,
    SignalDirection,
)
from app.infrastructure.database.models import RecommendationModel


def _recommendation() -> Recommendation:
    signal = LearningSignal(
        signal_id=uuid4(),
        feature="category",
        feature_value="history",
        metric="views",
        observed_value=Decimal("120"),
        baseline_value=Decimal("100"),
        delta=Decimal("20"),
        evidence=LearningEvidence(
            sample_size=6,
            baseline_available=True,
            data_quality_score=Decimal("0.95"),
        ),
        confidence=ConfidenceLevel.MEDIUM,
        direction=SignalDirection.POSITIVE,
        created_at=datetime(2026, 10, 5, 12, tzinfo=UTC),
    )
    return Recommendation(
        recommendation_id=uuid4(),
        signal=signal,
        text="Consider increasing reliance on this feature value.",
        status=RecommendationStatus.GENERATED,
        created_at=signal.created_at,
    )


def _model_from_recommendation(recommendation: Recommendation) -> RecommendationModel:
    signal = recommendation.signal
    return RecommendationModel(
        recommendation_id=recommendation.recommendation_id,
        signal_id=signal.signal_id,
        feature=signal.feature,
        feature_value=signal.feature_value,
        metric=signal.metric,
        observed_value=signal.observed_value,
        baseline_value=signal.baseline_value,
        delta=signal.delta,
        sample_size=signal.evidence.sample_size,
        baseline_available=signal.evidence.baseline_available,
        data_quality_score=signal.evidence.data_quality_score,
        notes=list(signal.evidence.notes),
        confidence=signal.confidence.value,
        direction=signal.direction.value,
        text=recommendation.text,
        status=recommendation.status.value,
        created_at=recommendation.created_at,
    )


def test_get_returns_persisted_recommendation() -> None:
    recommendation = _recommendation()
    session = MagicMock()
    session.scalar.return_value = _model_from_recommendation(recommendation)

    result = RecommendationQueryService(session).get(recommendation.recommendation_id)

    assert result == recommendation


def test_get_returns_none_when_missing() -> None:
    session = MagicMock()
    session.scalar.return_value = None

    result = RecommendationQueryService(session).get(uuid4())

    assert result is None


def test_list_rejects_non_positive_limit() -> None:
    with pytest.raises(ValueError, match="positive"):
        RecommendationQueryService(MagicMock()).list(limit=0)


def test_list_returns_mapped_recommendations() -> None:
    first = _recommendation()
    second = _recommendation()
    session = MagicMock()
    session.scalars.return_value.all.return_value = [
        _model_from_recommendation(first),
        _model_from_recommendation(second),
    ]

    result = RecommendationQueryService(session).list(
        status=RecommendationStatus.GENERATED,
        feature="category",
        metric="views",
        confidence=ConfidenceLevel.MEDIUM,
        direction=SignalDirection.POSITIVE,
        limit=10,
    )

    assert result == (first, second)
    statement = session.scalars.call_args.args[0]
    sql = str(statement)
    assert "recommendations.status" in sql
    assert "recommendations.feature" in sql
    assert "recommendations.metric" in sql
    assert "recommendations.confidence" in sql
    assert "recommendations.direction" in sql
    assert "LIMIT" in sql.upper()
