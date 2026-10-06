import pytest

from app.application.services.scene_timing import SceneTimingAllocator


def test_allocator_scales_all_scenes_to_tts_duration() -> None:
    allocator = SceneTimingAllocator()

    durations = allocator.allocate((6.0, 6.0, 6.0), 15.0)

    assert durations == pytest.approx((5.0, 5.0, 5.0))
    assert sum(durations) == pytest.approx(15.0)


def test_allocator_preserves_proportional_scene_weights() -> None:
    allocator = SceneTimingAllocator()

    durations = allocator.allocate((4.0, 8.0, 8.0), 30.0)

    assert durations == pytest.approx((6.0, 12.0, 12.0))


def test_allocator_enforces_minimum_scene_duration() -> None:
    allocator = SceneTimingAllocator(minimum_scene_duration=2.0)

    durations = allocator.allocate((1.0, 9.0), 6.0)

    assert durations[0] == pytest.approx(2.0)
    assert sum(durations) == pytest.approx(6.0)
    assert durations[1] == pytest.approx(4.0)


def test_allocator_rejects_impossible_target_duration() -> None:
    allocator = SceneTimingAllocator(minimum_scene_duration=2.0)

    with pytest.raises(ValueError, match="too short"):
        allocator.allocate((3.0, 3.0, 3.0), 5.0)


def test_normalize_for_narration_expands_short_storyboard():
    allocator = SceneTimingAllocator()
    durations = allocator.normalize_for_narration(
        (4.0, 8.0, 9.0, 5.0),
        (10, 20, 25, 18),
    )

    assert len(durations) == 4
    assert sum(durations) > 26.0
    for duration, words in zip(durations, (10, 20, 25, 18), strict=True):
        assert duration >= words / 2.5 * 1.05


def test_normalize_for_narration_preserves_planned_total_when_long_enough():
    allocator = SceneTimingAllocator()
    durations = allocator.normalize_for_narration(
        (8.0, 8.0, 8.0),
        (5, 8, 10),
    )

    assert sum(durations) == 24.0
    for duration, words in zip(durations, (5, 8, 10), strict=True):
        assert duration >= words / 2.5 * 1.05


def test_normalize_for_narration_rejects_mismatched_inputs():
    allocator = SceneTimingAllocator()

    with pytest.raises(ValueError, match="must match"):
        allocator.normalize_for_narration((4.0, 6.0), (10,))
