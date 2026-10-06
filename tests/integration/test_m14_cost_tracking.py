from decimal import Decimal

from sqlalchemy import select

from app.infrastructure.database.connection import get_session
from app.infrastructure.providers.reliability import CostTracker


def test_cost_tracker_persists_cost_event() -> None:
    from uuid import uuid4

    from app.infrastructure.database.models import CostEventModel

    session = get_session()
    try:
        run_id = uuid4()
        tracker = CostTracker(session)
        tracker.record(
            "gemini",
            "generate_script",
            Decimal("0.0123"),
            run_id=str(run_id),
            metadata={"request_id": "req-cost"},
        )
        event = session.scalar(select(CostEventModel).where(CostEventModel.run_id == run_id))
        assert event is not None
        assert event.provider == "gemini"
        assert event.operation == "generate_script"
        assert event.amount == Decimal("0.0123")
        assert event.cost_metadata == {"request_id": "req-cost"}
    finally:
        session.close()
