# Active Roadmap — M23–M38

## Baseline
M22 is the production-smoke baseline. Historical details: docs/M0-M22_PROJECT_HISTORY.md.

## M23 — Narrative Intelligence — COMPLETE
Goal: eliminate narrative repetition and make every sentence advance the story.
Deliverables:
- progression rules in script prompt
- NarrativeRedundancyGate
- exact duplicate detection
- conservative similarity checks
- hook/first-body repetition check
- adjacent sentence repetition check
- regression tests
- production integration
Exit: known hook/body repetition is rejected; legitimate paraphrases remain accepted; PR #128 merged; CI #738 passed on the M23 branch and CI #739 passed on main. Production smoke baseline remained green from the M22 production-smoke run; M23 changes are confined to script QA and do not alter render/provider behavior.

## M24 — Visual Retrieval 2.0
Goal: multi-query retrieval and candidate-pool ranking.
Flow: Scene Contract → Query Expansion → Candidate Pool → M17 ranking → M19 quality → M20/M25 semantic verification → final ranking.
Deliverables: primary/entity/action/context queries, canonical candidate pool, query/provider trace, ranking integration, bounded retry/fallback.
Exit: multiple candidates are evaluated per scene and selected assets are traceable.

## M25 — Real Vision Verification — COMPLETE
Goal: inspect actual image pixels.
Deliverables: Gemini multimodal vision verifier using the existing verifier contract; entity/action/context checks; must_show/must_avoid checks; confidence calibration; deterministic failover; bounded top-6 shortlist verification; traceable verifier identity and pixel-verification metadata.
Exit: actual image content affects decisions and the verifier is traceable.
Evidence: PR #130 merged; CI on the final M25 commit passed Static checks, Database/tests and Docker build.

## M26 — Visual Variety Engine — COMPLETE
Goal: reduce unnecessary repetition using candidate reuse, source reuse, composition, shot type and subject signals.
Rule: variety never overrides semantic correctness.
Deliverables: run-scoped bounded variety history; exact asset reuse detection; recent provider reuse penalty; composition and shot-type diversity signals; subject-token overlap scoring; bounded candidate reordering before the existing M25 semantic verification shortlist; variety audit metadata; regression coverage for reuse, diversity, empty history and bounded state.
Exit: duplicates are prevented where alternatives exist and low-candidate cases degrade gracefully.
Evidence: PR #131; final branch CI passed Static checks, Database/tests (419 passed) and Docker build. Production Gemini/MP4 smoke was not dispatched for M26; M25 production contract and CI baseline remain unchanged.

## M27 — Dynamic Subtitle Engine — COMPLETE
Goal: timed, readable, emphasis-aware Shorts captions.
Deliverables: deterministic word-level timestamps proportional to narration duration; bounded cue segmentation by word count, character count and punctuation; deterministic emphasis selection; 9:16 safe-area validation; dynamic ASS rendering; existing FFmpeg renderer integration; cue-level static fallback; regression and integration coverage.
Exit: captions align with narration timing, stay within validated safe-area constraints, and degrade to static cue rendering when dynamic timing/emphasis cannot be built.
Evidence: PR #132; final branch CI passed Static checks, Database/tests and Docker build. Production MP4 smoke/visual inspection was not dispatched for M27.

## M28 — Dynamic Camera Motion — COMPLETE
Goal: controlled motion for still visuals.
Initial motions: zoom in/out, pan left/right/up/down, subtle push/pull.
Selection uses scene purpose, duration and recent motion; normalized focus bounds keep motion conservative.
Deliverables: deterministic CameraMotionEngine; bounded push/pull and pan variants; recent-motion de-prioritization; short-beat static fallback; typed motion propagation through VideoSceneInput; FFmpeg zoompan integration for still images; M28 camera-motion audit metadata; regression coverage for planning and render contracts.
Exit: motion is bounded, deterministic, subject-safe within normalized focus constraints, and has a static fallback.
Evidence: PR #133 merged as main commit `4d8258a12af3534c2e214f99c5fb8f020a8cd4ea`; final branch CI #803 and main CI #806 passed Static checks, Database/tests and Docker build. Production MP4 smoke/visual inspection was not dispatched because the available workflow does not expose a production-smoke dispatch path; this remains an explicit validation caveat.

## M29 — Visual–Narration Synchronization — COMPLETE
Goal: unify narration, visual, caption and motion timing.
VisualBeat remains the source temporal contract, but final render timing is reconciled against the actual TTS duration.
Deliverables: UnifiedTimeline; synchronized scene/beat start/end times; proportional beat-duration reconciliation; automatic major scene-drift detection; caption cue coverage validation; render-input scene/beat identity; unified timing consumed by FFmpeg; synchronization audit metadata persisted with render results; regression and render integration coverage.
Exit: major timing drift is detected automatically, minor drift is reconciled without gaps/overlaps, caption cues remain inside the visual timeline, and one authoritative timeline drives final render durations.
Evidence: PR #134; final branch CI run #809 passed Static checks, Database/tests (443 passed) and Docker build. Production MP4 smoke/visual inspection was not dispatched because the available workflow does not expose a production-smoke dispatch path; this remains an explicit validation caveat.

## M30 — Automated Video Judge — COMPLETE
Goal: machine-check final video quality before Telegram approval.
Dimensions: technical, narrative, visual, audio, captions, synchronization and product quality.
Decisions: PASS, PASS_WITH_WARNINGS, RETRY, REJECT.

Deliverables:
- deterministic AutomatedVideoJudge
- seven-dimension quality scoring
- blocking failure detection
- PASS / PASS_WITH_WARNINGS / RETRY / REJECT decision policy
- M29 synchronization evidence consumption
- audio QC evidence consumption
- visual fallback coverage signal
- auditable QC stage metadata
- explicit retryable/permanent run-state routing before Telegram approval
- regression coverage for all decision classes
- M30 exit audit

Exit: generate → render/QC → judge → PASS/PASS_WITH_WARNINGS → Telegram approval, or RETRY → FAILED_RETRYABLE, or REJECT → FAILED_PERMANENT.

Evidence: PR #135; final branch CI run #835 passed Static checks, Database/tests and Docker build. Database/tests result: 449 passed. Production MP4 smoke/visual inspection was not dispatched because the available workflow does not expose a production-smoke dispatch path; this remains an explicit validation caveat.

## M31 — Judge-Driven Retry Orchestration — COMPLETE
Goal: turn M30 retry diagnoses into bounded, auditable retry plans.
Deliverables:
- JudgeDrivenRetryOrchestrator
- targeted visual/audio/synchronization retry actions
- bounded two-attempt retry budget
- action deduplication
- retry exhaustion escalation
- QC metadata persistence
- generation-pipeline routing for retryable vs permanent outcomes
- regression coverage for retry planning and exhaustion
- M31 exit audit

Exit: generate → render/QC → M30 Judge → RETRY → M31 plan → bounded retry state, while PASS/PASS_WITH_WARNINGS continue to Telegram approval.

Evidence: PR #136; final branch CI passed Static checks, Database/tests and Docker build. Production MP4 smoke/visual inspection was not dispatched because the available workflow does not expose a production-smoke dispatch path; this remains an explicit validation caveat.

## M32 — Judge-Driven Retry Execution Engine — COMPLETE
Goal: execute M31 retry plans against the real generation/render pipeline and re-judge the regenerated artifact.
Deliverables:
- JudgeDrivenRetryExecutionEngine
- real targeted visual reselection
- bounded audio repair and rerender
- M29 timeline reconciliation on retry renders
- automatic M30 re-judge after every retry
- two-attempt execution budget with terminal escalation
- retry execution audit metadata
- regression coverage for success, exhaustion and no-op paths
- M32 exit audit

Exit: M30 RETRY → M31 plan → M32 actual execution → rerender/QC → M30 re-judge → PASS/PASS_WITH_WARNINGS or bounded escalation.
Evidence: PR #137; final branch CI run #851 passed Static checks, Database/tests (457 passed) and Docker build. Production MP4 smoke/visual inspection was not dispatched because the available workflow does not expose a production-smoke dispatch path; this remains an explicit validation caveat.

## M33 — Adaptive Retry Policy — COMPLETE
Goal: measure retry effectiveness and avoid repeating interventions that do not improve the judged artifact.
Deliverables:
- AdaptiveRetryPolicy
- retry score and per-dimension effectiveness observations
- non-improving targeted-action exclusion
- safe regeneration fallback
- bounded three-attempt generation path
- effectiveness metadata persisted in QC
- regression coverage for adaptive selection and execution
- M33 exit audit

Exit: M30 RETRY → M31 plan → M32 execution → M30 re-judge → M33 effectiveness measurement → adapt next action set → bounded retry/pass.
Evidence: PR #138; final branch CI run #861 passed Static checks, Database/tests (461 passed) and Docker build. Production MP4 smoke/visual inspection was not dispatched because the available workflow does not expose a production-smoke dispatch path; this remains an explicit validation caveat.


## M35 — Measured Retry Economics & Checkpoint Reuse — COMPLETE
Goal: replace static retry-cost assumptions with measured execution telemetry and avoid re-executing successful retry work when the bounded retry loop revisits the same action bundle.

Deliverables:
- measured retry duration captured at the execution boundary
- RetryCostCalibration with minimum-sample protection and smoothed runtime calibration
- M34 economics ranking consumes calibrated costs when measured telemetry exists
- explicit distinction between observed runtime cost and the normalized fallback baseline
- checkpoint reuse metadata for successful retry action bundles
- later retries skip already-successful checkpoint actions instead of regenerating them
- regression coverage for calibration, measured ranking and checkpoint reuse
- M35 exit audit

Exit: M30 RETRY → M31 plan → M32 execution → M30 re-judge → M33 effectiveness → M34 gain/cost ranking → M35 measured cost calibration → reuse successful checkpoint work → bounded retry/pass.

Evidence: PR #140 merged to main as commit `23d13e00bc8d2669f626e3f9c622cb6e735987f8`. The workflow-run API exposed to this session returned no M35 run, so green CI is not claimed. Production MP4 smoke/visual inspection remains an explicit caveat until a production-smoke dispatch path is exposed.


## M34 — Retry Economics & Action Ranking — COMPLETE
Goal: choose retry interventions by expected quality gain per intervention cost and preserve successful intermediate work whenever possible.
Deliverables:
- RetryEconomicsPolicy with deterministic relative intervention costs
- expected quality-gain estimation from current judge deficits, retry-reason alignment and prior bundle evidence
- efficiency-based retry action ordering
- adaptive M33 actions fed into the economics ranking stage
- explicit preservation metadata for targeted actions not selected on the current retry
- retry economics metadata persisted in QC
- regression coverage for cost/gain ranking and preservation behavior

Exit: M30 RETRY → M31 plan → M32 execution → M30 re-judge → M33 effectiveness adaptation → M34 cost/benefit ranking → execute only the highest-value interventions → preserve untouched successful work → bounded retry/pass.

Evidence: PR #139; final branch CI run #868 passed Static checks, Database/tests (464 passed) and Docker build. Production MP4 smoke/visual inspection was not dispatched because the available workflow does not expose a production-smoke dispatch path; this remains an explicit validation caveat.

## M36 — Retry Outcome Learning — COMPLETE
Goal: learn from historical retry outcomes without making causal claims from bundled interventions.

Deliverables:
- isolated action-level retry outcome evidence model
- minimum-sample protection for learned signals
- recency-weighted success rate and quality-gain estimation
- confidence-bounded learning multiplier for retry economics
- historical effectiveness input accepted by the retry execution/economics path
- conservative exclusion of bundled and non-targeted regeneration evidence
- regression coverage for cold start, sparse evidence, recency weighting and learned ranking
- M36 exit audit

Exit: historical retry telemetry influences action ranking only when isolated evidence is sufficient; bundled observations remain bundle-level evidence; cold-start and sparse-data behavior falls back to deterministic M34/M35 economics.

Evidence: PR #141 merged to main as commit `8fe737b43efa9b7a3636cf42ff5558ad8ba4dcf0`. The exposed workflow API did not return a completed green conclusion before merge, so green CI is not claimed. Production MP4 smoke/visual inspection remains dependent on a workflow dispatch path that is not currently exposed.

## M37 — Provider Performance Learning — COMPLETE
Goal: learn provider reliability, latency and quality signals from historical telemetry and use them to improve eligible-provider routing without overriding circuit breakers or deterministic cold-start behavior.

Deliverables:
- provider performance observation contract
- minimum-sample and confidence protection
- capability/operation-scoped learning
- recency-weighted success-rate learning
- latency-aware provider ranking
- optional quality-score learning when provider metadata supplies a validated score
- bounded provider ranking multiplier
- StrategyRouter integration that preserves health/circuit-breaker eligibility
- executor support for historical provider telemetry
- regression coverage for cold start, scoping, recency, quality and routing
- M37 exit audit

Exit: providers with sufficient historical evidence can be ranked by measured reliability/latency/quality; sparse or missing history preserves declared provider order; unhealthy/open-circuit providers remain ineligible.

Evidence: PR #142 merged to main as commit `03e5a8562c2a76df06f860489f262cd9de781575`. No completed CI workflow run was exposed for the final M37 head during this session, so green CI is not claimed. Production provider/MP4 smoke remains dependent on a workflow dispatch path that is not currently exposed.

## M38 — Unified Quality / Reliability / Cost Optimization — COMPLETE
Goal: compose retry-action economics, historical action learning, provider performance learning and measured provider cost into one bounded action/provider decision score.

Deliverables:
- UnifiedOptimization decision service
- action + provider candidate ranking
- capability/operation-scoped measured provider cost evidence
- minimum-sample and confidence protection for provider cost
- bounded provider cost multiplier
- composition of M34/M35 action economics with M36/M37 learning
- deterministic cold-start and sparse-data behavior
- regression coverage for combined ranking and isolation
- M38 exit audit

Exit: a retry intervention and eligible provider can be ranked together from measured quality/reliability/cost evidence without bypassing existing health, circuit-breaker, retry-budget or checkpoint safeguards.

Evidence: implementation and focused regression coverage added on branch `feat/m38-unified-optimization`; final CI and merge evidence to be recorded after PR validation.

## Dependency
M23 → M24 → M25; M25 branches to M26 and M27; M26/M27 converge at M28/M29; M29 → M30 → M31 → M32 → M33 → M34 → M35 → M36 → M37 → M38. M26 and M27 can partly run in parallel.

## Priority
Current execution focus: M38 → M39 → M40 → M41 → M42.

## Definition of Done
Each milestone requires contract, implementation, unit tests, integration tests, failure tests, audit/observability, CI green, production smoke, actual MP4 inspection and documentation update.

## Final target
Topic → Research → Story Plan → Script → Narrative QA → Scene Contract → Multi-query Retrieval → Quality → Real Vision → Variety → TTS → Dynamic Captions → Motion → Unified Sync → Render → Video Judge → Judge → Retry Orchestration → Retry Execution → Re-judge → Adaptive Retry Policy → Retry/Pass → Telegram Approval → YouTube Publish.

The target is a measurable, auditable, failure-tolerant, quality-controlled short-form video production system.
