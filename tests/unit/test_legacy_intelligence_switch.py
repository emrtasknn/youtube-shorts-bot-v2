from types import SimpleNamespace
from typing import Any, cast

from app.application.use_cases.generate_custom_short import CustomShortRequest, GenerateCustomShort


def _service(enabled: bool) -> GenerateCustomShort:
    dummy = cast(Any, SimpleNamespace())
    return GenerateCustomShort(
        session=dummy,
        text=dummy,
        stock_media=dummy,
        tts=dummy,
        video_engine=dummy,
        downloader=dummy,
        intelligence_enabled=enabled,
    )


def _request() -> CustomShortRequest:
    marker = cast(Any, object())
    return CustomShortRequest(
        topic="t",
        run_key="k",
        production_decision=marker,
        topic_selection_decision=marker,
        experiment_variant=marker,
        experiment_assignment=marker,
        optimization_decision=marker,
    )


def test_overrides_dropped_when_disabled() -> None:
    req = _service(False).effective_request(_request())
    assert req.production_decision is None
    assert req.topic_selection_decision is None
    assert req.experiment_variant is None and req.experiment_assignment is None
    assert req.optimization_decision is None
    assert req.topic == "t"


def test_overrides_kept_when_enabled() -> None:
    original = _request()
    assert _service(True).effective_request(original) is original
