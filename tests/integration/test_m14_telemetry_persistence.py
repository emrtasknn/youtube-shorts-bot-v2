from uuid import uuid4

from sqlalchemy import select

from app.domain.enums import ContentCategory, EventSeverity, RunStatus, RunType
from app.infrastructure.database.connection import get_session
from app.infrastructure.database.models import ContentModel, RunModel, SystemEventModel
from app.infrastructure.providers.telemetry import ReliabilityTelemetry


def test_reliability_telemetry_persists_system_event() -> None:
    session = get_session()
    try:
        run_id = uuid4()
        content = ContentModel(
            content_key=f"telemetry-test-{run_id}",
            language="en",
            category=ContentCategory.CUSTOM,
            topic="Telemetry test",
        )
        session.add(content)
        session.flush()
        session.add(
            RunModel(
                id=run_id,
                run_key=f"telemetry-run-{run_id}",
                content_id=content.id,
                run_type=RunType.CUSTOM,
                status=RunStatus.RUNNING,
                language="en",
            )
        )
        session.flush()

        telemetry = ReliabilityTelemetry(session)
        telemetry.emit(
            "provider.success",
            EventSeverity.INFO,
            provider="gemini",
            message="Provider request succeeded",
            metadata={"request_id": "req-telemetry"},
            run_id=str(run_id),
        )

        event = session.scalar(select(SystemEventModel).where(SystemEventModel.run_id == run_id))
        assert event is not None
        assert event.event_type == "provider.success"
        assert event.severity == EventSeverity.INFO
        assert event.provider == "gemini"
        assert event.event_metadata == {"request_id": "req-telemetry"}
    finally:
        session.close()
