from decimal import Decimal

from app.infrastructure.database.connection import get_session
from app.infrastructure.providers.contracts import ProviderResult, ProviderUsage
from app.infrastructure.providers.reliability import DatabaseIdempotencyStore


def test_database_idempotency_survives_store_recreation() -> None:
    session = get_session()
    try:
        first = DatabaseIdempotencyStore(session, ttl_seconds=3600)
        result = ProviderResult(
            success=True,
            provider="primary",
            request_id="req-1",
            output={"text": "cached"},
            usage=ProviderUsage(input_units=2, output_units=3, total_units=5),
            cost=Decimal("0.0123"),
            latency_ms=42,
            metadata={"model": "test"},
        )
        first.put("restart-safe-key", result)

        second = DatabaseIdempotencyStore(session, ttl_seconds=3600)
        cached = second.get("restart-safe-key")

        assert cached == result
    finally:
        session.close()


def test_database_idempotency_expiry_is_removed() -> None:
    from datetime import UTC, datetime, timedelta

    session = get_session()
    try:
        store = DatabaseIdempotencyStore(session, ttl_seconds=1)
        now = datetime.now(UTC) - timedelta(seconds=2)
        result = ProviderResult(True, "primary", "req-expired")
        store.put("expired-key", result, now=now)

        assert store.get("expired-key") is None
    finally:
        session.close()
