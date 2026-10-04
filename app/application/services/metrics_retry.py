from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MetricsFailureKind(StrEnum):
    RETRYABLE = "RETRYABLE"
    PERMANENT = "PERMANENT"


@dataclass(frozen=True, slots=True)
class MetricsCollectionError:
    kind: MetricsFailureKind
    code: str
    message: str
    attempts: int


class MetricsCollectionException(RuntimeError):
    def __init__(self, failure: MetricsCollectionError) -> None:
        super().__init__(failure.message)
        self.failure = failure


class MetricsRetryPolicy:
    """Classifies analytics failures without performing implicit network retries."""

    RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})

    @classmethod
    def classify(cls, error: BaseException) -> MetricsFailureKind:
        import httpx

        if isinstance(error, (httpx.TimeoutException, httpx.NetworkError)):
            return MetricsFailureKind.RETRYABLE
        if isinstance(error, httpx.HTTPStatusError):
            if error.response.status_code in cls.RETRYABLE_STATUS_CODES:
                return MetricsFailureKind.RETRYABLE
            return MetricsFailureKind.PERMANENT
        if isinstance(error, (ValueError, TypeError)):
            return MetricsFailureKind.PERMANENT
        return MetricsFailureKind.RETRYABLE
