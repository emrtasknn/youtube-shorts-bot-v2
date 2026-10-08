# M33 Exit Audit — Adaptive Retry Policy

## Scope

M33 adds measured retry effectiveness to the M32 execution loop. Retry actions are no longer repeated blindly: each regenerated artifact is compared with the previous judge report, and non-improving targeted actions are excluded from later attempts.

## Runtime contract

`M30 Judge → M31 Plan → M32 Execute → M30 Re-Judge → M33 Measure → adapt next plan → execute only useful actions`

## Effectiveness signals

For every executed retry the system records:

- before score
- after score
- score delta
- improved/not improved
- per-dimension score deltas
- actions used for that attempt

The default improvement threshold is 1.0 judge-score point.

## Adaptive behavior

- First retry uses the M31 targeted plan unchanged.
- If a targeted action fails to improve the judge score, that action is excluded from the next retry.
- `REGENERATE_VIDEO` remains the safe general fallback.
- If targeted actions are exhausted, the policy falls back to general regeneration rather than repeating a known ineffective intervention.
- The execution budget is bounded at three total attempts in the M33 generation path.

## Observability

QC metadata now contains an `effectiveness` history alongside the existing retry-attempt records.

## Validation

Final branch CI run #861 passed Static checks, Database/tests (461 passed) and Docker build. The M33 regression suite covers:

- non-improving targeted action exclusion
- retaining actions that improve quality
- effectiveness history produced by the execution engine
- adaptive action change across attempts
- invalid policy threshold rejection

## Production validation caveat

Production MP4 smoke/visual inspection was not dispatched because the available workflow does not expose a production-smoke dispatch path. CI validates the adaptive retry contract and regression suite, but this does not constitute a new production MP4 visual sign-off.

## Next step

M34 should focus on retry economics and evidence-driven action ordering: estimate the cost of each intervention, prefer the highest expected quality gain per cost, and preserve successful intermediate assets when possible.
