# M3 — Pexels stock-media adapter

M3 starts real provider integration with Pexels as the first STOCK_MEDIA adapter.

## Scope

- Search photos through GET /v1/search.
- Search videos through GET /v1/videos/search.
- Normalize provider responses into a stable internal result shape.
- Convert HTTP failures into the provider error contract.
- Preserve Retry-After for HTTP 429.
- Keep credentials outside source control.
- Register the adapter only when explicitly enabled and an API key exists.

Pexels currently requires an API key in the Authorization header and supports up to 80 search results per request. Its API exposes request quota headers, so quota and rate telemetry can be added to the provider health layer without changing the adapter contract.

## Configuration

Set:

    PEXELS_ENABLED=true
    PEXELS_API_KEY=...
    PEXELS_BASE_URL=https://api.pexels.com
    PEXELS_TIMEOUT_SECONDS=30

If PEXELS_ENABLED=false or the key is missing, the provider is not registered.

The adapter does not download files or bypass attribution requirements. The normalized result keeps the provider/source URLs and photographer metadata for later asset persistence and attribution handling.

## Reliability

The adapter deliberately does not implement its own retry loop. HTTP 429, timeout, and transient network/server errors are translated into ProviderError; M2's ReliabilityExecutor remains responsible for retry, backoff, circuit breaking, rate limiting, quota handling, and fallback.

Source: Pexels API documentation.
