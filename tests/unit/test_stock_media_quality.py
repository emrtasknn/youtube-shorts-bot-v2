from app.application.services.stock_media_quality import StockMediaQualityEvaluator
from app.application.services.stock_media_scoring import StockMediaScore
from app.application.services.visual_quality import VisualQualityDecision


def _score(
    *,
    orientation: float,
    resolution: float,
    duration: float = 1.0,
) -> StockMediaScore:
    return StockMediaScore(
        score=0.0,
        relevance=0.9,
        orientation=orientation,
        resolution=resolution,
        duration=duration,
        duplicate_penalty=0.0,
        eligible=True,
        reasons=(),
    )


def test_m17_quality_signals_are_mapped_into_m19_contract() -> None:
    result = StockMediaQualityEvaluator().evaluate(_score(orientation=1.0, resolution=0.70))

    assert result.decision == VisualQualityDecision.ACCEPT
    assert result.score.overall == 0.865


def test_low_resolution_candidate_remains_beautifiable() -> None:
    result = StockMediaQualityEvaluator().evaluate(
        _score(orientation=1.0, resolution=0.35)
    )

    assert result.decision == VisualQualityDecision.BEAUTIFY
    assert result.score.beautifiable is True
