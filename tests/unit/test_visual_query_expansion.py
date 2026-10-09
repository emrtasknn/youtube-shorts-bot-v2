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
        "archive_subject",
        "archive_context",
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



def test_historical_query_expansion_prefers_subject_specific_archival_searches() -> None:
    scene = build_scene_contract(
        {
            "narration": "The reactor exploded at Chernobyl in 1986.",
            "visual_goal": "Show the Chernobyl Reactor 4 explosion",
            "visual_query": "Chernobyl Reactor 4 explosion radiation plume 1986",
            "purpose": "event",
            "subject": "Chernobyl Reactor 4 explosion",
            "action": "exploding",
            "entities": ["Chernobyl Reactor 4"],
            "location": "Chernobyl",
            "era": "1986",
            "visual_intent": "nuclear disaster",
            "visual_style": "documentary",
            "must_show": ["reactor structure", "explosion plume"],
            "must_avoid": ["modern industrial equipment"],
        }
    )

    queries = VisualQueryExpander().expand(scene).bounded_variants

    assert any("archival photograph" in item.query for item in queries)
    assert all("Chernobyl" in item.query for item in queries)
    assert not any(item.query == "historical illustration" for item in queries)
