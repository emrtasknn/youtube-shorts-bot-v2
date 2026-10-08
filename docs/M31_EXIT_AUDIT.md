# M31 Exit Audit — Judge-Driven Retry Orchestration

## Scope

M31 converts M30 retry signals into a bounded, auditable retry plan. It separates diagnosis from execution so the existing generation pipeline remains the owner of providers, assets and render resources.

## Contract

Retry reasons map to targeted actions:

- `excessive_visual_fallbacks` → reselect visuals
- `audio_qc_failed` → repair audio
- `synchronization_failed` → reconcile timeline
- every retryable plan → regenerate the final video
- unknown retry reason → bounded generic regeneration
- exhausted retry budget → escalate permanently

Default retry budget: **2 attempts total**.

## Runtime flow

`Render → M30 Judge → RETRY → M31 Retry Plan → targeted action set → bounded retry state`

The current generation use case persists the plan in QC stage metadata and routes the run to:

- `FAILED_RETRYABLE` when another attempt is allowed
- `FAILED_PERMANENT` when the retry budget is exhausted

PASS/PASS_WITH_WARNINGS continue to Telegram approval unchanged.

## Safety

- no unbounded retry loop
- duplicate actions are removed
- retry budget is explicit
- terminal exhaustion is auditable
- M30 remains the source of quality diagnosis
- provider/resource ownership stays in the generation pipeline

## Observability

QC stage metadata now records:

- attempt
- max_attempts
- retryable
- actions
- reasons
- terminal_reason
- next_status

## Validation

Unit coverage verifies:

- visual fallback targeting
- multi-reason action deduplication
- retry budget exhaustion
- non-retry decisions
- retry status selection

## Production validation caveat

Production MP4 smoke/visual inspection was not dispatched because the available workflow does not expose a production-smoke dispatch path. M31 therefore has CI/test evidence but no new production MP4 visual sign-off.

## Follow-up

A future execution adapter can consume the persisted M31 action plan to automatically invoke the targeted provider/render operations. Keeping that executor separate prevents M31 from duplicating the existing generation pipeline.
