from __future__ import annotations

from app.application.ports.stock_media import (
    StockMediaGateway,
    StockMediaSearchRequest,
    StockMediaSearchResult,
)
from app.application.ports.text_generation import (
    TextGenerationGateway,
    TextGenerationRequest,
    TextGenerationResult,
)
from app.application.ports.tts import TTSGateway, TTSRequest, TTSResult
from app.infrastructure.providers.contracts import (
    ProviderCapability,
    ProviderRequest,
)
from app.infrastructure.providers.executor import ReliabilityExecutor


class ProviderTextGenerationGateway(TextGenerationGateway):
    def __init__(self, executor: ReliabilityExecutor, providers: list[str]) -> None:
        self._executor = executor
        self._providers = providers

    async def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
        result = await self._executor.execute(
            ProviderRequest(
                request_id=request.request_id,
                run_id=request.run_id,
                capability=ProviderCapability.TEXT_GENERATION,
                operation="generate_text",
                provider=self._providers[0],
                model=request.model,
                payload={
                    "prompt": request.prompt,
                    "system_instruction": request.system_instruction,
                    "generation_config": request.generation_config,
                },
                idempotency_key=f"{request.run_id}:text:{request.request_id}",
            ),
            candidates=self._providers,
        )
        output = result.output or {}
        return TextGenerationResult(
            provider=result.provider,
            text=str(output.get("text", "")),
            model=output.get("model"),
            metadata=result.metadata,
        )


class ProviderTTSGateway(TTSGateway):
    def __init__(self, executor: ReliabilityExecutor, providers: list[str]) -> None:
        self._executor = executor
        self._providers = providers

    async def synthesize(self, request: TTSRequest) -> TTSResult:
        result = await self._executor.execute(
            ProviderRequest(
                request_id=request.request_id,
                run_id=request.run_id,
                capability=ProviderCapability.TTS,
                operation="text_to_speech",
                provider=self._providers[0],
                model=request.model,
                payload={"text": request.text, "format": request.format},
                idempotency_key=f"{request.run_id}:tts:{request.request_id}",
            ),
            candidates=self._providers,
        )
        output = result.output or {}
        return TTSResult(
            provider=result.provider,
            audio_bytes=bytes(output.get("audio_bytes", b"")),
            format=str(output.get("format", request.format)),
            metadata=result.metadata,
        )


class ProviderStockMediaGateway(StockMediaGateway):
    def __init__(self, executor: ReliabilityExecutor, providers: list[str]) -> None:
        self._executor = executor
        self._providers = providers

    async def search(self, request: StockMediaSearchRequest) -> StockMediaSearchResult:
        result = await self._executor.execute(
            ProviderRequest(
                request_id=request.request_id,
                run_id=request.run_id,
                capability=ProviderCapability.STOCK_MEDIA,
                operation=request.operation,
                provider=(request.provider_candidates or self._providers)[0],
                payload={
                    "query": request.query,
                    "page": request.page,
                    "per_page": request.per_page,
                    "orientation": request.orientation,
                },
                idempotency_key=f"{request.run_id}:stock:{request.request_id}",
            ),
            candidates=list(request.provider_candidates or self._providers),
        )
        output = result.output or {}
        return StockMediaSearchResult(
            provider=result.provider,
            query=request.query,
            items=list(output.get("items", [])),
            total_results=int(output.get("total_results", 0)),
            metadata=result.metadata,
        )
