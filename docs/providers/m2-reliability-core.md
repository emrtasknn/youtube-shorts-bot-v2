# M2 — Reliability Core

M2 establishes the provider-agnostic execution boundary for the V2 system.

## Scope

- Provider request/result/error contracts
- Provider registry and capability discovery
- Retry classification, Retry-After, exponential backoff and jitter
- Token-bucket rate limiting
- Provider concurrency limits
- Quota accounting
- Circuit breakers and provider health
- Ordered fallback with loop protection
- Idempotency/deduplication
- Cost tracking
- Reliability telemetry
- Deterministic fake providers and failure-mode tests

Real provider SDKs are intentionally out of scope. They are introduced in M3 as adapters behind these contracts.

## Execution boundary

`Application -> ReliabilityExecutor -> Registry -> Health/Quota/Rate/Concurrency -> Adapter -> External API`

No application use case should import a provider SDK directly.

## Failure behavior

- 429 / transient / timeout: retry with Retry-After or exponential backoff + jitter.
- Quota exhaustion: stop retrying the exhausted provider and fall back.
- Permanent/auth/invalid request: do not retry.
- Provider health opens a circuit after repeated failures.
- A provider already attempted in the current execution cannot be selected again.
- Successful idempotent requests are cached to prevent duplicate paid operations.
