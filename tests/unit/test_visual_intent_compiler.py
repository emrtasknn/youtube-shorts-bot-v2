from app.application.services.scene_contract import build_scene_contract
from app.application.services.visual_intent import VisualIntentCompiler


def test_action_is_not_promoted_to_hard_must_show_requirement() -> None:
    scene = build_scene_contract(
        {
            "narration": "The general issued orders to the soldiers.",
            "visual_goal": "Show Roman military leadership in an ancient setting.",
            "visual_query": "ancient Roman general soldiers",
            "subject": "Roman general",
            "entities": ["Roman general", "Roman soldiers"],
            "action": "issuing orders",
            "era": "ancient Rome",
            "must_show": ["Roman general", "issuing orders", "Roman soldiers"],
            "must_avoid": ["modern military"],
        }
    )

    intent = VisualIntentCompiler().compile(scene)

    assert "issuing orders" not in intent.must_show
    assert "Roman general" in intent.must_show
    assert "Roman soldiers" in intent.must_show
    assert intent.action == "issuing orders"
    assert intent.must_avoid == ("modern military",)
