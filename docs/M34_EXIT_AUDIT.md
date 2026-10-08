# M34 Exit Audit — Retry Economics & Action Ranking

## Scope

M34 adds a deterministic economics layer after M33 adaptive retry selection. The retry loop now prefers interventions with the highest expected judge-quality gain per relative intervention cost instead of executing actions in a fixed order.

## Runtime contract

`M30 Judge → M31 Plan → M32 Execute → M30 Re-Judge → M33 Measure/Adapt → M34 Rank by gain/cost → execute → bounded retry/pass`

## Economics model

Each retry action has a normalized engineering cost representing relative intervention effort:

- `REPAIR_AUDIO`: 1.5
- `RECONCILE_TIMELINE`: 1.0
- `REGENERATE_VIDEO`: 2.5
- `RESELECT_VISUALS`: 4.0
- `ESCALATE`: terminal/non-executing fallback

Expected gain combines:

- current judge dimension deficit for the action's target dimension
- alignment between the judge retry reason and the action
- prior positive score improvement observed for that action

Historical observations are treated as **bundle evidence, not causal attribution**, because M32/M33 may execute multiple actions together.

## Preservation behavior

M34 does not rerun targeted interventions that are not selected by the economics ranking. The decision records those untouched targeted actions as preserved, allowing successful intermediate assets/work to remain intact instead of being needlessly regenerated.

## Observability

QC metadata now contains:

- ranked action order
- estimated intervention cost
- expected quality gain
- gain/cost efficiency
- preserved targeted actions
- economics decision reason

## Validation

M34 adds regression coverage for:

- audio repair being preferred when audio quality is the dominant deficit
- visual reselection being preferred when visual quality is the dominant deficit
- preservation metadata for untouched targeted actions

The existing M33 retry-engine suite continues to validate bounded execution and adaptive behavior.

## Production validation caveat

Production MP4 smoke/visual inspection is still dependent on a workflow dispatch path that is not currently exposed. CI validates the economics contract and regression suite, but this does not constitute a new production MP4 visual sign-off.

## Next step

M35 should focus on measured retry cost calibration from real provider/render telemetry and, where safe, stronger checkpoint-level artifact reuse.
