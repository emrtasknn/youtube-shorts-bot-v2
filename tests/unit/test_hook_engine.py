from app.application.services.hook_engine import HookEngine


def test_engine_classifies_unanswered_question() -> None:
    result = HookEngine().evaluate("Why did the Roman fleet disappear?")

    assert result.hook_type == "unanswered_question"
    assert result.is_acceptable
    assert "question" in result.signals


def test_engine_classifies_shocking_fact() -> None:
    result = HookEngine().evaluate("Only one person survived the disaster.")

    assert result.hook_type in {"shocking_fact", "impossible_event"}
    assert result.is_acceptable
    assert result.score >= 0.55


def test_engine_rejects_generic_hook() -> None:
    result = HookEngine().evaluate("Today we are talking about ancient Rome.")

    assert result.hook_type == "generic"
    assert not result.is_acceptable


def test_engine_rejects_overlong_hook() -> None:
    result = HookEngine().evaluate(
        "This is a very long opening sentence that keeps explaining the story "
        "before giving the viewer any reason to keep watching."
    )

    assert result.hook_type == "generic"
    assert not result.is_acceptable


def test_engine_fallback_creates_question_hook() -> None:
    hook = HookEngine().fallback("The Mary Celeste mystery")

    assert hook == "What really happened with The Mary Celeste mystery?"
    assert HookEngine().ensure_acceptable(hook).hook_type == "unanswered_question"
