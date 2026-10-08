# M37 Exit Audit — Provider Performance Learning

## Scope

M37 adds conservative provider-level learning to the existing reliability/router layer. It uses historical provider telemetry to improve eligible-provider ordering while preserving health checks, circuit breakers, fallback behavior and deterministic cold-start routing.

## Runtime contract

`historical provider telemetry → capability/operation scope → recency-weighted provider evidence → bounded ranking → StrategyRouter eligibility → provider execution`

## Evidence model

A provider observation contains:

- provider
- capability
- operation
- success/failure
- latency
- optional validated quality score

Learning is scoped by capability and operation so a provider's TTS performance cannot incorrectly influence text-generation routing.

## Learning behavior

M37 calculates:

- recency-weighted success rate
- median latency
- optional average quality score
- confidence based on minimum samples

The provider ranking multiplier is bounded to 0.75–1.25 and is neutral for missing or insufficient evidence.

## Reliability integration

StrategyRouter first evaluates circuit-breaker/health eligibility. Historical learning can only reorder eligible providers; it cannot revive an unhealthy provider or bypass existing retry/fallback rules.

ReliabilityExecutor accepts historical provider telemetry explicitly. Current-run observations are appended to the supplied history and remain separate from persistent storage ownership.

## Quality signal

Quality is optional. It is consumed only when provider metadata exposes a numeric `quality_score`; absence of quality data falls back to reliability and latency signals.

## Validation

Regression coverage includes:

- minimum-sample cold start
- capability/operation scoping
- recency weighting
- optional quality signal
- unknown-provider neutral behavior
- learned router ordering
- deterministic router fallback without learning
- existing health eligibility remains authoritative

## Production validation caveat

PR #142 was merged to main as commit `03e5a8562c2a76df06f860489f262cd9de781575`. No completed CI workflow run was exposed for the final M37 head during this session, so green CI is not claimed. Production provider/MP4 smoke remains dependent on a workflow dispatch path that is not currently exposed.

## Exit criterion

M37 is complete when sufficient historical provider evidence can improve eligible-provider ranking, while sparse data preserves deterministic behavior and unhealthy providers remain excluded.
