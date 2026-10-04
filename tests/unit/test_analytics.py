from datetime import UTC, datetime

import pytest

from app.application.ports.analytics import VideoPerformance


def test_video_performance_accepts_normalized_metrics() -> None:
    measured_at = datetime.now(UTC)
    performance = VideoPerformance(
        publication_id="publication-1",
        platform="YOUTUBE",
        platform_post_id="video-1",
        measured_at=measured_at,
        views=12000,
        likes=450,
        comments=37,
        shares=91,
        subscribers_gained=28,
        watch_time_seconds=54000.0,
        average_view_duration_seconds=18.0,
        retention=0.72,
    )

    assert performance.views == 12000
    assert performance.retention == 0.72
    assert performance.to_dict()["platform_post_id"] == "video-1"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("views", -1),
        ("likes", -1),
        ("comments", -1),
        ("shares", -1),
        ("subscribers_gained", -1),
        ("watch_time_seconds", -1.0),
        ("average_view_duration_seconds", -1.0),
        ("retention", -0.01),
        ("retention", 1.01),
    ],
)
def test_video_performance_rejects_invalid_metric(field: str, value: float) -> None:
    kwargs: dict[str, object] = {
        "publication_id": "publication-1",
        "platform": "YOUTUBE",
        "platform_post_id": "video-1",
        "measured_at": datetime.now(UTC),
        field: value,
    }

    with pytest.raises(ValueError):
        VideoPerformance(**kwargs)


@pytest.mark.parametrize(
    "field",
    ["publication_id", "platform", "platform_post_id"],
)
def test_video_performance_requires_identity(field: str) -> None:
    kwargs: dict[str, object] = {
        "publication_id": "publication-1",
        "platform": "YOUTUBE",
        "platform_post_id": "video-1",
        "measured_at": datetime.now(UTC),
        field: "",
    }

    with pytest.raises(ValueError):
        VideoPerformance(**kwargs)


def test_video_performance_allows_unavailable_optional_metrics() -> None:
    performance = VideoPerformance(
        publication_id="publication-1",
        platform="YOUTUBE",
        platform_post_id="video-1",
        measured_at=datetime.now(UTC),
    )

    assert performance.views == 0
    assert performance.watch_time_seconds is None
    assert performance.average_view_duration_seconds is None
    assert performance.retention is None
