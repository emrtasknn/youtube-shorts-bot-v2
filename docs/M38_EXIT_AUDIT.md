# M38 Exit Audit — Unified Quality / Reliability / Cost Optimization

## Scope

M38 composes the learning and economics signals built in M34–M37 into one bounded decision layer. The objective is to rank a retry intervention together with an eligible provider using the best available evidence without allowing sparse history to destabilize production behavior.

## Runtime contract

`M30 judge → M31 retry plan → M33 adaptation → M34/M35 action economics → M36 historical action learning + M37 provider learning → M38 unified action/provider decision → bounded execution`

M38 is intentionally a decision service rather than a second provider/router implementation. Existing retry orchestration, provider health, circuit breakers, fallback and retry budgets remain authoritative.

## Unified decision model

Each decision contains:

- retry action
- candidate provider, when provider candidates are supplied
- M34/M35 action economics
- M37 learned provider performance
- measured provider cost evidence
- bounded decision score
- combined confidence
- auditable reason

The score is:

`action efficiency × provider performance multiplier × measured-cost multiplier`

All learned multipliers are bounded. Missing or insufficient provider evidence remains neutral.

## Provider cost learning

M38 introduces `ProviderCostObservation` and derives:

- capability/operation-scoped median measured cost
- minimum-sample protection
- confidence
- bounded cost multiplier

Cost means observed provider execution/billing telemetry supplied by the caller; M38 does not invent vendor pricing.

## Safety and reliability invariants

- sparse provider history does not change the cold-start decision materially
- provider evidence cannot cross capability/operation boundaries
- unhealthy/open-circuit providers remain excluded by the existing StrategyRouter
- M38 does not bypass retry budgets or checkpoint reuse
- provider cost influence is bounded to 0.75–1.25
- negative cost observations are ignored
- action economics remains the source of retry-action quality/cost ranking

## Validation

Regression coverage includes:

- cold-start neutral behavior
- provider performance + measured cost changing the preferred candidate
- capability/operation isolation
- sparse cost evidence
- invalid/negative cost evidence
- bounded provider cost influence

## Implementation

- `app/application/services/unified_optimization.py`
- `tests/unit/test_unified_optimization.py`
- `docs/M38_EXIT_AUDIT.md`

## Validation caveat

The local environment available during implementation cannot resolve GitHub externally, so the repository test suite could not be executed locally. The implementation was kept isolated and covered with focused regression tests; final CI remains the authoritative execution check.

Production MP4/provider smoke remains dependent on the workflow dispatch path that is not currently exposed.

## Exit criterion

M38 is complete when action economics, provider performance and measured provider cost can be composed into a single bounded ranking decision, while cold-start, sparse-data, capability isolation and reliability safeguards remain deterministic.
