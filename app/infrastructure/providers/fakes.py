from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal

from app.infrastructure.providers.contracts import (
    ProviderCapability,
    ProviderError,
    ProviderRequest,
    ProviderResult,
)


class FakeProvider:
    def __init__(
        self,
        name: str,
        capabilities: frozenset[ProviderCapability],
        handler: Callable[[ProviderRequest], ProviderResult | Awaitable[ProviderResult]],
    ) -> None:
        self.name = name
        self.capabilities = capabilities
        self.handler = handler
        self.calls = 0

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        self.calls += 1
        result = self.handler(request)
        if hasattr(result, "__await__"):
            return await result
        return result


def success_result(request: ProviderRequest, output: str = "ok") -> ProviderResult:
    return ProviderResult(
        success=True,
        provider=request.provider,
        request_id=request.request_id,
        output=output,
        cost=Decimal("0.001"),
    )


def transient_error(provider: str, code: str = "UPSTREAM_503") -> ProviderError:
    return ProviderError(
        code=code,
        category="TRANSIENT",
        provider=provider,
        message="temporary failure",
        retryable=True,
    )
