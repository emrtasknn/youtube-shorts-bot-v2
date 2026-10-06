from app.application.services.scene_contract import build_scene_contract
from app.application.services.visual_beat import VisualBeatCompiler
from app.application.services.visual_beat_retrieval import to_visual_relevance_context


def test_visual_beat_maps_to_existing_m17_retrieval_context() -> None:
    scene = build_scene_contract(
        {
            "narration": "Rome expanded across the Mediterranean.",
            "visual_goal": "Show Roman expansion",
            "visual_query": "Roman Empire expansion",
            "entities": ["Rome", "Roman Empire"],
            "location": "Mediterranean",
            "era": "ancient Rome",
            "action": "expanding",
            "must_show": ["Roman territory"],
            "must_avoid": ["modern borders"],
        }
    )
    beat = VisualBeatCompiler().compile(
        scene,
        scene_index=0,
        scene_duration_seconds=6.0,
    ).beats[0]

    context = to_visual_relevance_context(beat)

    assert context.entities == scene.entities
    assert context.location == scene.location
    assert context.era == scene.era
    assert context.visual_goal == scene.visual_goal
    assert context.action == scene.action
    assert context.must_show == scene.must_show
    assert context.must_avoid == scene.must_avoid
