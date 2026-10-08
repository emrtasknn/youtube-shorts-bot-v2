# M30 Exit Audit — Automated Video Judge

## Scope
M30 adds a deterministic post-render decision layer between rendering/QC and Telegram approval. It does not replace M29 synchronization or the low-level VideoQualityGate.

## Contract
The judge evaluates seven dimensions:
- technical
- narrative
- visual
- audio
- captions
- synchronization
- product quality

It returns exactly one decision:
- PASS
- PASS_WITH_WARNINGS
- RETRY
- REJECT

Decision policy:
- blocking technical/narrative/visual/synchronization failures → REJECT
- excessive visual fallback or unresolved audio QC → RETRY
- clean high-scoring output → PASS
- acceptable output with non-blocking warnings → PASS_WITH_WARNINGS

## Runtime flow
Generate → TTS → M29 unified render → VideoQualityGate → AudioQualityAnalyzer → M30 AutomatedVideoJudge → PASS / PASS_WITH_WARNINGS → Telegram Approval

or

→ RETRY → FAILED_RETRYABLE

or

→ REJECT → FAILED_PERMANENT

## Evidence consumed
- final MP4 path
- final duration, resolution and FPS
- audio stream presence
- M29 synchronization metadata
- narration word count
- scene count and visual coverage
- audio QC result
- visual fallback count
- subtitle payload
- Shorts duration ceiling

## Observability
The judge report is persisted in the existing QC stage metadata under m30_automated_video_judge:
- decision
- overall score
- per-dimension scores
- failures
- warnings
- retry reasons
- evaluated output path
- fallback count

No new database migration is required.

## Validation
Unit coverage includes:
- clean PASS
- PASS_WITH_WARNINGS for non-blocking synchronization warnings
- RETRY for excessive visual fallback
- RETRY for audio QC failure
- REJECT for technical failures
- REJECT for blocking synchronization failures

The generation use case is wired so approval is created only for PASS/PASS_WITH_WARNINGS. RETRY and REJECT terminate before Telegram approval with explicit run statuses.

## Production validation caveat
Production MP4 smoke/visual inspection was not dispatched because the available GitHub workflow does not expose a production-smoke dispatch path. M30 therefore has CI/test evidence but not a newly generated production MP4 visual sign-off.