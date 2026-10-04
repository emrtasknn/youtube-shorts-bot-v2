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
