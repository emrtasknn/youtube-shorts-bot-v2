from app.application.services.narrative_redundancy import NarrativeRedundancyGate


def _payload(**overrides):
    payload = {
        "hook": "One decision changed the entire battle.",
        "body": (
            "The commander moved his ships through the narrow channel before dawn. "
            "The maneuver cut the enemy fleet off from its supply route. "
            "Without reinforcements, the defenders were forced to retreat before sunset."
        ),
        "scenes": [
            {"narration": "One decision changed the entire battle."},
            {"narration": "The commander moved his ships through the narrow channel before dawn."},
            {"narration": "The maneuver cut the enemy fleet off from its supply route."},
            {"narration": "Without reinforcements, the defenders were forced to retreat before sunset."},
        ],
    }
    payload.update(overrides)
    return payload


def test_gate_accepts_progressive_narrative():
    report = NarrativeRedundancyGate().evaluate(_payload())
    assert report.passed is True
    assert report.failures == ()
    assert report.compared_pairs > 0


def test_gate_rejects_exact_duplicate():
    report = NarrativeRedundancyGate().evaluate(
        _payload(
            body=(
                "The commander moved his ships through the narrow channel before dawn. "
                "The commander moved his ships through the narrow channel before dawn. "
                "The defenders retreated before sunset."
            )
        )
    )
    assert report.passed is False
    assert "exact duplicate" in report.failures[0]
    assert "exact_duplicate" in report.signals


def test_gate_rejects_hook_first_body_repetition():
    report = NarrativeRedundancyGate().evaluate(
        _payload(
            hook="The commander moved his ships through the narrow channel before dawn.",
            body=(
                "The commander moved his ships through the narrow channel before dawn. "
                "That move cut the enemy fleet from its supply route. "
                "The defenders retreated before sunset."
            ),
        )
    )
    assert report.passed is False
    assert any("hook repeats the first body claim" in failure for failure in report.failures)
    assert "hook_body_repetition" in report.signals


def test_gate_rejects_adjacent_high_similarity():
    report = NarrativeRedundancyGate().evaluate(
        _payload(
            body=(
                "The commander moved his ships through the narrow channel before dawn. "
                "The commander moved his ships through the narrow channel before sunrise. "
                "The defenders were forced to retreat before sunset."
            )
        )
    )
    assert report.passed is False
    assert any("adjacent narrative sentences" in failure for failure in report.failures)


def test_gate_accepts_legitimate_paraphrase_with_new_information():
    report = NarrativeRedundancyGate().evaluate(
        _payload(
            body=(
                "The commander moved his ships through the narrow channel before dawn. "
                "That maneuver cut the enemy fleet away from its supply route. "
                "The defenders then lost their reinforcements and retreated before sunset."
            )
        )
    )
    assert report.passed is True
