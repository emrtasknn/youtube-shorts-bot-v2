# M39 Exit Audit — Production Provider Telemetry Learning

## Scope

M39 closes the historical-evidence gap identified after M37/M38: provider learning can now reconstruct durable provider performance and measured-cost evidence from production system events instead of relying only on caller-supplied in-memory history.

## Architecture

`ReliabilityExecutor → ReliabilityTelemetry → PostgreSQL SystemEventModel → ProductionProviderTelemetryStore → M37/M38 learning inputs`

The existing telemetry persistence path is reused. No parallel telemetry database is introduced.

## Durable evidence

Provider success events now persist:

- provider
- capability
- operation
- latency_ms
- measured cost
- optional quality_score
- request/attempt metadata

Provider error events now persist:

- provider
- capability
- operation
- retry/error category
- zero latency fallback when the provider fails before a measured successful execution

## Reconstruction

`ProductionProviderTelemetryStore` converts persisted `provider.success` / `provider.error` events into:

- `ProviderPerformanceObservation`
- `ProviderCostObservation`

Evidence is scoped by capability and operation, ordered deterministically, and incomplete provider events are ignored.

## Runtime integration

`ReliabilityExecutor` can receive an optional `ProductionProviderTelemetryStore`. When configured, durable historical provider evidence is loaded before routing and combined with explicitly supplied historical observations.

This means a fresh process can learn from prior production runs instead of starting from an empty in-memory history.

## Safety

- Existing circuit breakers remain authoritative.
- Existing health checks and fallback remain authoritative.
- M37 minimum samples and bounded ranking remain unchanged.
- M38 cost learning remains bounded and ignores negative costs.
- Durable telemetry is evidence only; it does not directly mutate provider health.
- No schema migration is required because the existing durable SystemEventModel is reused.

## Validation

Focused regression coverage verifies:

- persisted success/error events reconstruct performance observations
- measured cost is reconstructed
- capability/operation filtering works
- provider filtering works
- incomplete evidence is ignored

## Files

- `app/infrastructure/providers/production_telemetry.py`
- `app/infrastructure/providers/executor.py`
- `tests/unit/test_production_telemetry.py`
- `docs/M39_EXIT_AUDIT.md`

## Validation caveat

Local pytest execution is unavailable in the current environment because external GitHub/DNS access is unavailable. CI remains authoritative. Production MP4 smoke remains dependent on the currently unavailable production-smoke dispatch path.

## Exit criterion

M39 is complete when provider learning can reconstruct durable production telemetry and feed it into the existing M37 routing/M38 optimization evidence path without weakening reliability safeguards.
