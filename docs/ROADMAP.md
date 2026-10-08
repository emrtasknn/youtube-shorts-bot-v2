# Active Roadmap — M23–M30

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

## M25 — Real Vision Verification
Goal: inspect actual image pixels.
Deliverables: vision provider using existing verifier contract, entity/action/context checks, must_show/must_avoid checks, confidence calibration, failover and cost-aware shortlist verification.
Exit: actual image content affects decisions and the verifier is traceable.

## M26 — Visual Variety Engine
Goal: reduce unnecessary repetition using candidate reuse, source reuse, composition, shot type and subject signals.
Rule: variety never overrides semantic correctness.
Exit: duplicates are prevented where alternatives exist and low-candidate cases degrade gracefully.

## M27 — Dynamic Subtitle Engine
Goal: timed, readable, emphasis-aware Shorts captions.
Deliverables: word timestamps, segmentation, emphasis selection, safe-area validation, renderer integration and static fallback.
Exit: captions align with narration and do not overflow.

## M28 — Dynamic Camera Motion
Goal: controlled motion for still visuals.
Initial motions: zoom in/out, pan left/right/up/down, subtle push/pull.
Selection uses scene purpose, composition, duration and recent motion.
Exit: motion is bounded, deterministic, subject-safe and has a static fallback.

## M29 — Visual–Narration Synchronization
Goal: unify narration, visual, caption and motion timing.
VisualBeat is the temporal contract.
Checks: duration, semantic focus, caption timing, motion duration, transition timing and drift.
Exit: major timing drift is detected automatically and one timeline drives render inputs.

## M30 — Automated Video Judge
Goal: machine-check final video quality before Telegram approval.
Dimensions: technical, narrative, visual, audio, captions, synchronization and product quality.
Decisions: PASS, PASS_WITH_WARNINGS, RETRY, REJECT.
Exit: generate → judge → accept/retry/reject works end-to-end.

## Dependency
M23 → M24 → M25; M25 branches to M26 and M27; M26/M27 converge at M28/M29; M29 → M30. M26 and M27 can partly run in parallel.

## Priority
Tier 1: M23, M24, M25, M29, M30.
Tier 2: M26, M27.
Tier 3: M28.

## Definition of Done
Each milestone requires contract, implementation, unit tests, integration tests, failure tests, audit/observability, CI green, production smoke, actual MP4 inspection and documentation update.

## Final target
Topic → Research → Story Plan → Script → Narrative QA → Scene Contract → Multi-query Retrieval → Quality → Real Vision → Variety → TTS → Dynamic Captions → Motion → Unified Sync → Render → Video Judge → Retry/Pass → Telegram Approval → YouTube Publish.

The target is a measurable, auditable, failure-tolerant, quality-controlled short-form video production system.
