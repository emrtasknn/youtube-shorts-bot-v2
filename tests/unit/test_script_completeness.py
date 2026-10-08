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
                "narration": (
                    "The result transformed movie history forever and became a lasting turning point."
                ),
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


def test_gate_rejects_sentence_fragment():
    payload = _payload(
        body=(
            "In 1927 Hollywood audiences heard synchronized dialogue for the first time. "
            "The breakthrough changed how studios made movies and quickly pushed silent films aside. "
            "Studios rushed to adapt, actors faced a new challenge, and audiences discovered a different kind of cinema, and."
        )
    )
    report = ScriptCompletenessGate().evaluate(payload)
    assert report.passed is False
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


def test_gate_accepts_paraphrased_storyboard_with_full_narration():
    payload = _payload(
        body=(
            "In 1453 Ottoman forces breached Constantinople after a long siege. "
            "Mehmed II used massive cannons and ships to pressure the city from land and sea. "
            "The final assault broke Byzantine defenses, ending centuries of Roman rule in the East. "
            "The conquest reshaped the region and became a turning point in world history."
        ),
        scenes=[
            {"narration": "A city thought impossible to conquer finally fell.", "purpose": "hook", "duration": 4},
            {"narration": "Mehmed II surrounded Constantinople and attacked from multiple directions during the siege.", "purpose": "context", "duration": 7},
            {"narration": "Ottoman cannons battered the walls while ships entered the harbor, overwhelming Byzantine defenses.", "purpose": "event", "duration": 8},
            {"narration": "The fall ended Byzantine rule and changed the balance of power across the region.", "purpose": "payoff", "duration": 6},
        ],
    )
    report = ScriptCompletenessGate().evaluate(payload)
    assert report.passed is True
    assert not any("storyboard vocabulary coverage" in failure for failure in report.failures)


def test_gate_uses_scene_narration_for_scene_timing():
    payload = _payload(
        hook="This hook is intentionally much longer than the storyboard opening.",
        body=(
            "In 1927 Hollywood audiences heard synchronized dialogue for the first time. "
            "The breakthrough changed how studios made movies and quickly pushed silent films aside. "
            "The result transformed movie history forever and became a lasting turning point."
        ),
        cta="Follow for more detailed history and historical stories.",
        scenes=[
            {
                "narration": "A shocking fact happened.",
                "purpose": "hook",
                "duration": 4,
            },
            {
                "narration": "In 1927 Hollywood audiences heard synchronized dialogue for the first time.",
                "purpose": "context",
                "duration": 7,
            },
            {
                "narration": "The breakthrough changed how studios made movies and quickly pushed silent films aside.",
                "purpose": "event",
                "duration": 8,
            },
            {
                "narration": "The result transformed movie history forever.",
                "purpose": "payoff",
                "duration": 5,
            },
        ],
    )
    report = ScriptCompletenessGate().evaluate(payload)
    assert report.passed is True
    assert not any("scene duration" in failure for failure in report.failures)
