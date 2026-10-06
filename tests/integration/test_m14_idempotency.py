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


def test_database_idempotency_duplicate_put_is_race_safe() -> None:
    from sqlalchemy import func, select

    from app.infrastructure.database.models import ProviderIdempotencyModel

    session = get_session()
    try:
        first = DatabaseIdempotencyStore(session)
        first_result = ProviderResult(True, "primary", "req-first")
        second_result = ProviderResult(True, "fallback", "req-second")

        first.put("concurrent-key", first_result)
        first.put("concurrent-key", second_result)

        cached = first.get("concurrent-key")
        count = session.scalar(
            select(func.count())
            .select_from(ProviderIdempotencyModel)
            .where(ProviderIdempotencyModel.idempotency_key == "concurrent-key")
        )

        assert cached == first_result
        assert count == 1
    finally:
        session.close()
