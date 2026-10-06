from pathlib import Path
from uuid import uuid4

from app.application.services.audio_direction import AudioDirector
from app.application.services.autonomous_audio import AutonomousAudioPlanner


def test_autonomous_audio_generates_one_traceable_mix(tmp_path: Path) -> None:
    direction = AudioDirector().plan(
        hook="A shocking explosion",
        body="The city was suddenly hit by a massive wave.",
    )

    plan = AutonomousAudioPlanner().build(
        run_id=uuid4(),
        direction=direction,
        scenes=({"scene_index": 0, "narration": direction.tts_text},),
        duration_seconds=5,
        output_dir=tmp_path,
    )

    assert plan.background_audio_path.name == "background-mix.wav"
    assert plan.background_audio_path.is_file()
    assert plan.metadata["audio_variants_generated"] == 1
    assert plan.metadata["music"]["license"] == "original-procedural"
    assert plan.profile.startswith("m15:")
