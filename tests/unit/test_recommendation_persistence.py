from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.application.services.recommendation_persistence import RecommendationPersistenceService
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
            notes=("comparable baseline",),
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


def test_save_persists_recommendation_snapshot() -> None:
    session = MagicMock()
    session.scalar.return_value = None
    recommendation = _recommendation()

    result = RecommendationPersistenceService(session).save(recommendation)

    assert result == recommendation
    model = session.add.call_args.args[0]
    assert isinstance(model, RecommendationModel)
    assert model.recommendation_id == recommendation.recommendation_id
    assert model.signal_id == recommendation.signal.signal_id
    assert model.feature == "category"
    assert model.feature_value == "history"
    assert model.metric == "views"
    assert model.observed_value == Decimal("120")
    assert model.baseline_value == Decimal("100")
    assert model.delta == Decimal("20")
    assert model.sample_size == 6
    assert model.baseline_available is True
    assert model.data_quality_score == Decimal("0.95")
    assert model.notes == ["comparable baseline"]
    assert model.confidence == "MEDIUM"
    assert model.direction == "POSITIVE"
    assert model.status == "GENERATED"
    session.flush.assert_called_once()


def test_save_is_idempotent_for_existing_recommendation() -> None:
    session = MagicMock()
    recommendation = _recommendation()
    session.scalar.return_value = _model_from_recommendation(recommendation)

    result = RecommendationPersistenceService(session).save(recommendation)

    assert result.recommendation_id == recommendation.recommendation_id
    assert result.signal.signal_id == recommendation.signal.signal_id
    session.add.assert_not_called()
    session.flush.assert_not_called()


def test_save_many_preserves_order() -> None:
    session = MagicMock()
    session.scalar.return_value = None
    first = _recommendation()
    second = _recommendation()

    result = RecommendationPersistenceService(session).save_many((first, second))

    assert result == (first, second)
    assert session.add.call_count == 2
    assert session.flush.call_count == 2


def test_parse_recommendation_id_requires_uuid() -> None:
    with pytest.raises(ValueError, match="valid UUID"):
        RecommendationPersistenceService.parse_recommendation_id("recommendation-1")
