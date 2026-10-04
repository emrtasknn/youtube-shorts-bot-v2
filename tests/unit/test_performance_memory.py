from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.performance_memory import (
    PerformanceMemory,
    PerformanceProductionFeatures,
)


def make_features() -> PerformanceProductionFeatures:
    return PerformanceProductionFeatures(
        category="HISTORY_FACT",
        language="en",
        topic="The fall of Constantinople",
        angle="The final breach",
        hook="How did the city finally fall?",
        duration_target_seconds=Decimal("34.00"),
        word_count=92,
        scene_count=6,
        visual_providers=("pexels", "pixabay"),
        tts_provider="fish_audio",
        production_strategy="custom_single_vertical_slice",
    )


def test_production_features_are_immutable() -> None:
    features = make_features()

    with pytest.raises(AttributeError):
        features.topic = "changed"  # type: ignore[misc]


def test_performance_memory_requires_stable_publication_identity() -> None:
    memory = PerformanceMemory(
        publication_id=uuid4(),
        run_id=uuid4(),
        content_id=uuid4(),
        script_id=uuid4(),
        platform="YOUTUBE",
        platform_post_id="video-123",
        published_at=datetime(2026, 10, 4, tzinfo=UTC),
        features=make_features(),
    )

    assert memory.features.category == "HISTORY_FACT"
    assert memory.features.scene_count == 6
    assert memory.platform_post_id == "video-123"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("category", ""),
        ("language", ""),
        ("topic", ""),
    ],
)
def test_required_production_features_cannot_be_empty(field: str, value: str) -> None:
    values = {
        "category": "HISTORY_FACT",
        "language": "en",
        "topic": "A topic",
    }
    values[field] = value

    with pytest.raises(ValueError):
        PerformanceProductionFeatures(**values)


def test_production_feature_counts_must_be_non_negative() -> None:
    with pytest.raises(ValueError):
        PerformanceProductionFeatures(
            category="HISTORY_FACT",
            language="en",
            topic="A topic",
            word_count=-1,
        )

    with pytest.raises(ValueError):
        PerformanceProductionFeatures(
            category="HISTORY_FACT",
            language="en",
            topic="A topic",
            scene_count=-1,
        )


def test_memory_requires_platform_post_id() -> None:
    with pytest.raises(ValueError):
        PerformanceMemory(
            publication_id=uuid4(),
            run_id=uuid4(),
            content_id=uuid4(),
            script_id=uuid4(),
            platform="YOUTUBE",
            platform_post_id="",
            published_at=datetime(2026, 10, 4, tzinfo=UTC),
            features=make_features(),
        )
