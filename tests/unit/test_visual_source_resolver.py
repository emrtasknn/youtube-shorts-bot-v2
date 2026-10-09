import pytest

from app.application.services.scene_contract import build_scene_contract
from app.application.services.visual_source_resolver import VisualSourceResolver


def _scene(**overrides: object):
    data = {
        "narration": "The Roman Forum was the center of public life.",
        "visual_goal": "Show the Roman Forum as a historical location.",
        "visual_query": "Roman Forum ancient Rome ruins",
        "location": "Rome",
        "era": "ancient Rome",
        "entities": ["Roman Forum"],
        "must_show": ["forum ruins"],
        "must_avoid": ["modern skyline"],
    }
    data.update(overrides)
    return build_scene_contract(data)


def test_resolver_returns_stock_plan_without_calling_provider() -> None:
    plan = VisualSourceResolver().resolve(_scene())

    assert plan.kind == "stock"
    assert plan.exact_query == "Roman Forum ancient Rome ruins"
    assert any("archival photograph" in query for query in plan.broader_queries)
    assert any("historical photograph" in query for query in plan.broader_queries)
    assert all("Roman Forum" in query for query in plan.broader_queries)
    assert "historical illustration" not in plan.broader_queries
    assert plan.reason == "stock_selected_with_explicit_must_show_constraints"


def test_resolver_deduplicates_broader_queries() -> None:
    scene = _scene(
        visual_goal="historical illustration",
        location="",
        era="",
        must_show=[],
        entities=[],
    )

    plan = VisualSourceResolver().resolve(scene)

    assert plan.broader_queries == (
        "historical illustration",
        "Roman Forum ancient Rome ruins documentary photograph",
    )


def test_resolver_rejects_empty_visual_query() -> None:
    with pytest.raises(ValueError, match="visual_query"):
        VisualSourceResolver().resolve(_scene(visual_query=""))
