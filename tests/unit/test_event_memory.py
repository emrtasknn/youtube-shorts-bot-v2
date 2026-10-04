import pytest

from app.application.services.event_memory import EventMemoryCandidate


def test_event_id_is_deterministic_for_same_event_identity() -> None:
    first = EventMemoryCandidate.build_event_id(
        canonical_title="Mary Celeste Mystery",
        date="1872-12-04",
        location="Atlantic Ocean",
    )
    second = EventMemoryCandidate.build_event_id(
        canonical_title="Mary Celeste Mystery",
        date="1872-12-04",
        location="Atlantic Ocean",
    )
    assert first == second
    assert first.startswith("evt_")


def test_candidate_normalizes_payload_lists() -> None:
    candidate = EventMemoryCandidate.from_payload(
        {
            "canonical_title": "Mary Celeste",
            "aliases": ["Ghost Ship Mary Celeste", " Mary Celeste Crew Disappearance "],
            "entities": ["Mary Celeste", "Mary Celeste crew"],
            "core_facts": ["Found abandoned"],
            "claims": ["Crew disappeared"],
            "sources": ["https://example.com/source"],
            "status": "NEW_EVENT",
        },
        fallback_title="unused",
    )
    assert candidate.canonical_title == "Mary Celeste"
    assert candidate.aliases == (
        "Ghost Ship Mary Celeste",
        "Mary Celeste Crew Disappearance",
    )
    assert candidate.status == "NEW_EVENT"


def test_missing_event_id_is_derived() -> None:
    candidate = EventMemoryCandidate.from_payload(
        {"canonical_title": "Mary Celeste"},
        fallback_title="unused",
    )
    assert candidate.event_id.startswith("evt_")


def test_invalid_status_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported event memory status"):
        EventMemoryCandidate.from_payload(
            {"canonical_title": "Unknown event", "status": "ACCEPTED"},
            fallback_title="unused",
        )


def test_empty_canonical_title_is_rejected() -> None:
    with pytest.raises(ValueError, match="canonical_title"):
        EventMemoryCandidate.from_payload(
            {"canonical_title": ""},
            fallback_title="",
        )
