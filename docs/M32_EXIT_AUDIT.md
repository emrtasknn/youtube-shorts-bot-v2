# M32 Exit Audit — Judge-Driven Retry Execution Engine

## Scope

M32 turns the M31 retry plan into a real, bounded execution loop. A retry plan now invokes the existing visual/provider/render pipeline, produces a new artifact, runs QC and M30 again, and stops on PASS/PASS_WITH_WARNINGS or retry-budget exhaustion.

## Runtime contract

`Generate → Render/QC → M30 Judge → M31 Plan → M32 Execute → Render/QC → M30 Judge → PASS / second retry / escalation`

Targeted actions:

- `reselect_visuals` re-runs the existing visual retrieval/fallback path.
- `repair_audio` reduces the background bed and tightens ducking before rerender.
- `reconcile_timeline` relies on the existing M29 synchronization resolver during rerender.
- `regenerate_video` always completes the retry plan by producing a new render.

## Safety

- default maximum remains two total attempts
- no unbounded retry loop
- M31 remains the source of retry policy
- M30 remains the source of quality diagnosis
- existing provider and renderer instances remain owned by the generation use case
- each retry is re-judged before the run can continue

## Observability

QC metadata now records:

- retry attempt number
- executed action set
- retry decision and score
- retry reasons
- fallback count
- audio QC result
- synchronization evidence
- final decision
- exhaustion/terminal reason

## Validation

The M32 unit suite verifies:

- targeted retry execution
- second-attempt success
- second-attempt failure and budget exhaustion
- non-RETRY reports never invoke the executor

The generation integration routes actual visual reselection, audio repair, timeline reconciliation through the existing render pipeline rather than a mock-only executor.

## Production validation caveat

Production MP4 smoke/visual inspection was not dispatched because the available workflow does not expose a production-smoke dispatch path. CI validates the retry execution contract and regression suite, but this does not constitute a new production MP4 visual sign-off.

## Next step

M33 should focus on retry economics and quality-aware policy hardening: avoid repeating an action that did not improve the judge score, preserve successful intermediate assets, and record per-action effectiveness.
