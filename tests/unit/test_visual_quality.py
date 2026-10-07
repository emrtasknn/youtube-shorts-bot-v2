from __future__ import annotations

import pytest

from app.application.services.visual_quality import (
    VisualQualityDecision,
    VisualQualityEvaluator,
    VisualQualityPolicy,
    VisualQualityScore,
)


def test_high_quality_asset_is_accepted() -> None:
    result = VisualQualityEvaluator().evaluate(
        composition=0.9,
        resolution=0.95,
        portrait_fit=0.9,
        cleanliness=0.9,
        beautifiable=False,
    )

    assert result.decision == VisualQualityDecision.ACCEPT
    assert result.score.overall >= 0.75


def test_medium_quality_asset_is_marked_for_beautification() -> None:
    result = VisualQualityEvaluator().evaluate(
        composition=0.65,
        resolution=0.7,
        portrait_fit=0.65,
        cleanliness=0.6,
        beautifiable=True,
    )

    assert result.decision == VisualQualityDecision.BEAUTIFY


def test_medium_quality_asset_without_beautification_is_degraded_accept() -> None:
    result = VisualQualityEvaluator().evaluate(
        composition=0.65,
        resolution=0.65,
        portrait_fit=0.6,
        cleanliness=0.6,
        beautifiable=False,
    )

    assert result.decision == VisualQualityDecision.ACCEPT_DEGRADED


def test_low_quality_asset_is_rejected() -> None:
    result = VisualQualityEvaluator().evaluate(
        composition=0.2,
        resolution=0.3,
        portrait_fit=0.2,
        cleanliness=0.3,
        beautifiable=False,
    )

    assert result.decision == VisualQualityDecision.REJECT


def test_quality_score_rejects_out_of_range_values() -> None:
    with pytest.raises(ValueError, match="overall"):
        VisualQualityScore(
            composition=0.8,
            resolution=0.8,
            portrait_fit=0.8,
            cleanliness=0.8,
            overall=1.1,
            beautifiable=True,
        )


def test_policy_rejects_invalid_threshold_order() -> None:
    with pytest.raises(ValueError, match="thresholds"):
        VisualQualityPolicy(
            accept_threshold=0.5,
            beautify_threshold=0.6,
            degraded_floor=0.4,
        )
