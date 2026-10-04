from unittest.mock import Mock

from app.application.services.event_memory import EventMemoryCandidate
from app.application.services.novelty_hardening import NoveltyHardeningService


def candidate(
    *,
    event_id: str,
    title: str,
    date: str | None = None,
    location: str | None = None,
    entities: tuple[str, ...] = (),
    aliases: tuple[str, ...] = (),
) -> EventMemoryCandidate:
    return EventMemoryCandidate(
        event_id=event_id,
        canonical_title=title,
        aliases=aliases,
        date=date,
        location=location,
        entities=entities,
    )


def test_new_event_is_accepted() -> None:
    memory = Mock()
    memory.get.return_value = None
    memory.find_match.return_value = None

    decision = NoveltyHardeningService(memory).evaluate(
        candidate(event_id="evt_new", title="New Historical Event")
    )

    assert decision.status == "NEW"
    assert decision.accepted is True
    assert decision.reason == "no_strong_event_match"


def test_same_event_id_is_rejected() -> None:
    memory = Mock()
    existing = candidate(event_id="evt_same", title="Known Event")
    memory.get.return_value = existing

    decision = NoveltyHardeningService(memory).evaluate(existing)

    assert decision.status == "DUPLICATE"
    assert decision.accepted is False
    assert decision.matched_event_id == "evt_same"


def test_same_name_and_context_is_rejected() -> None:
    memory = Mock()
    existing = candidate(
        event_id="evt_known",
        title="The Great Fire",
        date="1666-09-02",
        location="London",
        entities=("London", "Great Fire"),
    )
    memory.get.return_value = None
    memory.find_match.return_value = existing

    decision = NoveltyHardeningService(memory).evaluate(
        candidate(
            event_id="evt_other",
            title="Great Fire of London",
            date="1666-09-02",
            location="London",
            entities=("London",),
        )
    )

    assert decision.status == "DUPLICATE"
    assert decision.accepted is False


def test_name_match_with_different_date_is_not_blocked() -> None:
    memory = Mock()
    existing = candidate(
        event_id="evt_old",
        title="The Great Fire",
        date="1666-09-02",
        location="London",
        entities=("London",),
    )
    memory.get.return_value = None
    memory.find_match.return_value = existing

    decision = NoveltyHardeningService(memory).evaluate(
        candidate(
            event_id="evt_other",
            title="The Great Fire",
            date="1700-01-01",
            location="London",
            entities=("London",),
        )
    )

    assert decision.status == "UNCERTAIN"
    assert decision.accepted is True


def test_name_match_without_context_is_rejected() -> None:
    memory = Mock()
    existing = candidate(event_id="evt_old", title="Mary Celeste")
    memory.get.return_value = None
    memory.find_match.return_value = existing

    decision = NoveltyHardeningService(memory).evaluate(
        candidate(event_id="evt_other", title="Mary Celeste")
    )

    assert decision.status == "DUPLICATE"
    assert decision.accepted is False
