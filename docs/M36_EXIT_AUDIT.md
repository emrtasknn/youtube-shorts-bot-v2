# M36 Exit Audit — Retry Outcome Learning

## Scope

M36 adds conservative historical learning to the M35 retry-economics layer. The goal is to improve future action ranking from accumulated retry outcomes without attributing a bundled intervention's score change to one action.

## Runtime contract

`M30 Judge → M31 Plan → M32 Execute → M30 Re-Judge → M33 Measure/Adapt → M34 Rank → M35 Calibrate/Reuse → M36 Learn isolated outcomes → bounded retry/pass`

## Evidence model

M36 treats an observation as action-level evidence only when exactly one targeted action was executed:

- `RESELECT_VISUALS`
- `REPAIR_AUDIO`
- `RECONCILE_TIMELINE`

Bundled observations remain excluded from action-level learning. `REGENERATE_VIDEO` and `ESCALATE` are also excluded because they do not provide safe targeted attribution.

## Learning behavior

The learning service calculates:

- sample count
- recency-weighted success rate
- recency-weighted positive score gain
- median runtime duration
- confidence bounded by minimum sample count
- a bounded expected-gain multiplier

Cold-start and insufficient-sample cases return the neutral multiplier `1.0`, preserving the deterministic M34/M35 behavior.

Historical learning is intentionally bounded to a 0.5–1.5 multiplier and cannot bypass the existing retry budget or action selection constraints.

## Integration

The retry execution engine accepts historical effectiveness observations from the caller and forwards them to retry economics. This keeps persistence ownership outside the retry engine and allows the production runtime to connect its existing QC/telemetry storage without introducing a second persistence system.

## Validation

Regression coverage includes:

- minimum-sample cold start
- recency-weighted learning
- exclusion of bundled evidence
- weak/non-improving historical evidence
- learned ranking in retry economics
- existing M35 duration and checkpoint behavior

## Production validation caveat

PR #141 was merged to main as commit `8fe737b43efa9b7a3636cf42ff5558ad8ba4dcf0`. The PR CI run was in progress at merge time and the exposed workflow API did not return a completed green conclusion before merge, so green CI is not claimed here. Production MP4 smoke/visual inspection remains dependent on a workflow dispatch path that is not currently exposed.

## Exit criterion

M36 is considered complete when isolated historical retry evidence can influence economics ranking, sparse data safely falls back to deterministic behavior, and bundled evidence cannot create false action-level attribution.
