# M35 Exit Audit — Measured Retry Economics & Checkpoint Reuse

## Scope

M35 hardens the M34 retry-economics layer with measured execution telemetry and safe checkpoint reuse.

## Runtime contract

`M30 Judge → M31 Plan → M32 Execute → M30 Re-Judge → M33 Measure/Adapt → M34 Rank → M35 Calibrate Cost / Reuse Checkpoint → bounded retry/pass`

## Measured cost calibration

Retry execution now records wall-clock duration around the injected retry executor.

The calibration layer:
- requires a configurable minimum number of measured samples before changing baseline costs
- uses median duration to reduce sensitivity to outliers
- treats bundle duration as shared evidence for the actions executed in that bundle
- applies bounded, smoothed adjustment to M34 normalized costs
- falls back to the deterministic M34 baseline when telemetry is absent or insufficient

This is explicitly runtime-cost telemetry, not provider billing or currency accounting.

## Checkpoint reuse

When a retry action bundle improves the judged score, the bundle becomes the current reusable checkpoint.

If a later bounded retry proposes the same successful actions again, those actions are skipped and recorded as `reused_checkpoint_actions`. The executor therefore retains ownership of provider/render resources while the retry engine prevents unnecessary re-execution.

Because observations are bundle-level evidence, M35 does not claim causal attribution to individual actions.

## Observability

Retry QC/effectiveness data now carries:
- measured retry duration
- calibrated economics reason when measured telemetry is available
- checkpoint reuse metadata on retry attempts

## Validation

Regression coverage includes:
- minimum-sample calibration fallback
- measured cost calibration
- retry duration capture
- successful checkpoint reuse on a later retry
- existing bounded retry behavior and no-op PASS behavior

## Production validation caveat

PR #140 was merged to main as commit `23d13e00bc8d2669f626e3f9c622cb6e735987f8`. The GitHub workflow-run API exposed to this session returned no run for the M35 merge commit, so a green CI run is not claimed here. Production MP4 smoke/visual inspection remains dependent on a workflow dispatch path that is not currently exposed.

## Next step

M36 should use accumulated retry telemetry for broader action-level attribution only when the runtime can collect isolated intervention measurements safely; otherwise keep bundle-level evidence conservative.
