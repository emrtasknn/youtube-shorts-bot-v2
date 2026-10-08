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

The repository's currently exposed workflow path does not provide a production-smoke dispatch route for real MP4 inspection. Therefore M36 can validate the deterministic learning contract through CI, but production visual smoke remains an explicit follow-up requirement.

## Exit criterion

M36 is considered complete when isolated historical retry evidence can influence economics ranking, sparse data safely falls back to deterministic behavior, and bundled evidence cannot create false action-level attribution.
