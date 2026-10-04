import pytest

from app.application.services.scene_contract import build_scene_contract


def test_build_scene_contract_normalizes_optional_fields() -> None:
    contract = build_scene_contract(
        {
            "narration": "Romans gathered.",
            "visual_goal": "Roman forum gathering",
            "visual_query": "Roman Forum Rome",
        }
    )

    assert contract.purpose == "support_narration"
    assert contract.subject == "Roman Forum Rome"
    assert contract.visual_intent == "Roman forum gathering"
    assert contract.visual_style == "documentary"
    assert contract.entities == ()
    assert contract.to_dict()["must_show"] == []


def test_build_scene_contract_preserves_structured_visual_constraints() -> None:
    contract = build_scene_contract(
        {
            "narration": "The fleet arrived.",
            "visual_goal": "Historical fleet arriving at port",
            "visual_query": "Spanish Armada Lisbon 1588",
            "purpose": "establish_event",
            "subject": "Spanish Armada fleet",
            "action": "arriving",
            "entities": ["Spanish Armada", "Lisbon"],
            "location": "Lisbon",
            "era": "1588",
            "visual_intent": "show the fleet approaching the harbor",
            "visual_style": "historical illustration",
            "must_show": ["ships", "harbor"],
            "must_avoid": ["modern vessels"],
        }
    )

    assert contract.entities == ("Spanish Armada", "Lisbon")
    assert contract.must_show == ("ships", "harbor")
    assert contract.must_avoid == ("modern vessels",)
    assert contract.location == "Lisbon"
    assert contract.era == "1588"


def test_build_scene_contract_rejects_missing_required_fields() -> None:
    with pytest.raises(ValueError, match="visual_query"):
        build_scene_contract({"narration": "Text", "visual_goal": "Goal", "visual_query": ""})


def test_build_scene_contract_rejects_non_list_constraints() -> None:
    with pytest.raises(ValueError, match="entities"):
        build_scene_contract(
            {
                "narration": "Text",
                "visual_goal": "Goal",
                "visual_query": "Specific query",
                "entities": "not-a-list",
            }
        )
