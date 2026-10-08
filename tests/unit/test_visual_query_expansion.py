from app.application.services.scene_contract import build_scene_contract
from app.application.services.visual_query_expansion import VisualQueryExpander


def _scene():
    return build_scene_contract(
        {
            "narration": "Rome expanded across the Mediterranean.",
            "visual_goal": "Show Roman expansion",
            "visual_query": "Roman Empire Mediterranean expansion",
            "purpose": "event",
            "subject": "Roman Empire",
            "action": "expanding",
            "entities": ["Rome", "Roman Empire"],
            "location": "Mediterranean",
            "era": "ancient Rome",
            "visual_intent": "territorial expansion",
            "visual_style": "documentary",
            "must_show": ["Roman territory"],
            "must_avoid": ["modern borders"],
        }
    )


def test_query_expander_creates_primary_entity_action_and_context_queries() -> None:
    plan = VisualQueryExpander().expand(_scene())

    assert [variant.name for variant in plan.bounded_variants] == [
        "primary",
        "entity_action",
        "entity_context",
        "goal_context",
        "contextual",
    ]
    assert plan.bounded_variants[0].query == "Roman Empire Mediterranean expansion"
    assert "expanding" in plan.bounded_variants[1].query
    assert all(variant.query.strip() for variant in plan.bounded_variants)
    assert len({variant.query.lower() for variant in plan.bounded_variants}) == 5


def test_query_expander_is_bounded_and_deduplicates_empty_variants() -> None:
    scene = build_scene_contract(
        {
            "narration": "A city changed.",
            "visual_goal": "Show the city",
            "visual_query": "city",
            "purpose": "support_narration",
            "subject": "city",
            "action": "",
            "entities": [],
            "location": "",
            "era": "",
            "must_show": ["city"],
            "must_avoid": [],
        }
    )

    plan = VisualQueryExpander().expand(scene)

    assert len(plan.bounded_variants) <= 5
    assert plan.bounded_variants[0].name == "primary"
    assert len({variant.query.lower() for variant in plan.bounded_variants}) == len(
        plan.bounded_variants
    )
