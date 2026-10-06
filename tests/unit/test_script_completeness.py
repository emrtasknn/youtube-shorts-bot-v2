from app.application.services.script_completeness import ScriptCompletenessGate


def _payload(**overrides):
    body = (
        "In 1927 Hollywood audiences heard synchronized dialogue for the first time. "
        "The breakthrough changed how studios made movies and quickly pushed silent films aside. "
        "Studios rushed to adapt, actors faced a new challenge, and audiences discovered a different kind of cinema. "
        "The result transformed movie history forever."
    )
    payload = {
        "hook": "A shocking fact happened.",
        "body": body,
        "cta": "Follow for more history.",
        "duration_target": 24,
        "scenes": [
            {
                "narration": "A shocking fact happened.",
                "purpose": "hook",
                "duration": 4,
            },
            {
                "narration": "In 1927 Hollywood audiences heard synchronized dialogue for the first time.",
                "purpose": "context",
                "duration": 6,
            },
            {
                "narration": "The breakthrough changed how studios made movies and quickly pushed silent films aside. Studios rushed to adapt, actors faced a new challenge, and audiences discovered a different kind of cinema.",
                "purpose": "event",
                "duration": 9,
            },
            {
                "narration": "The result transformed movie history forever.",
                "purpose": "payoff",
                "duration": 5,
            },
        ],
    }
    payload.update(overrides)
    return payload


def test_gate_accepts_complete_story():
    report = ScriptCompletenessGate().evaluate(_payload())
    assert report.passed is True
    assert report.failures == ()


def test_gate_rejects_truncated_body():
    payload = _payload(
        body=(
            "In 1927 Hollywood audiences heard synchronized dialogue for the first time, "
            "changing the movie industry"
        )
    )
    report = ScriptCompletenessGate().evaluate(payload)
    assert report.passed is False
    assert "body does not end with a complete sentence" in report.failures
    assert "body ends with a sentence fragment" in report.failures


def test_gate_rejects_short_story():
    payload = _payload(body="Hollywood heard voices in movies for the first time.")
    report = ScriptCompletenessGate().evaluate(payload)
    assert report.passed is False
    assert any("body is too short" in failure for failure in report.failures)


def test_gate_rejects_short_scene_narration():
    payload = _payload(
        scenes=[
            {"narration": "A shocking fact happened.", "purpose": "hook", "duration": 4},
            {"narration": "Hollywood changed.", "purpose": "event", "duration": 4},
            {"narration": "Cinema changed forever.", "purpose": "payoff", "duration": 4},
        ]
    )
    report = ScriptCompletenessGate().evaluate(payload)
    assert report.passed is False
    assert any("scene narration covers only" in failure for failure in report.failures)


def test_gate_requires_story_beats():
    payload = _payload(
        scenes=[
            {
                "narration": "A shocking fact happened.",
                "purpose": "support_narration",
                "duration": 4,
            },
            {
                "narration": "Hollywood changed movies.",
                "purpose": "support_narration",
                "duration": 8,
            },
            {"narration": "Cinema changed forever.", "purpose": "support_narration", "duration": 8},
        ]
    )
    report = ScriptCompletenessGate().evaluate(payload)
    assert report.passed is False
    assert any("narrative beats" in failure for failure in report.failures)
