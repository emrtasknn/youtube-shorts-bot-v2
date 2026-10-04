from uuid import uuid4

import pytest

from app.application.services.performance_snapshot import PerformanceSnapshotService


def test_service_requires_uuid_publication_id() -> None:
    with pytest.raises(ValueError, match="valid UUID"):
        PerformanceSnapshotService(None).list_for_publication("publication-1")


def test_service_rejects_non_positive_limit() -> None:
    service = PerformanceSnapshotService(None)
    with pytest.raises(ValueError, match="positive"):
        service.list_for_publication(str(uuid4()), limit=0)
