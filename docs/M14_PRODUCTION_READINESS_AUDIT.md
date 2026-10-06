# M14.0 — Production Readiness Audit

**Status:** AUDIT COMPLETE / IMPLEMENTATION REQUIRED  
**Audit date:** 2026-10-06  
**Base:** `main` after M13 exit  
**Scope:** M0–M13 production readiness before final hardening

## 1. Audit objective

M14 is the final production-hardening milestone. It must not add uncontrolled product features or bypass the existing M10/M11/M12/M13 decision boundaries.

The audit checks whether the current repository can safely operate the full lifecycle:

`run → generation → QC → Telegram approval → YouTube publication → performance memory → experimentation → controlled optimization`

## 2. Existing strengths

### 2.1 Domain state machine
The repository already has explicit run, stage, approval and publication state machines.

Run states include:
- CREATED / QUEUED / RUNNING
- RESEARCHING / TOPIC_VALIDATION / SCRIPTING / STORYBOARDING
- ASSET_PLANNING / ASSET_GENERATION / TTS / AUDIO_MIX / RENDERING / QC
- READY_FOR_APPROVAL / APPROVED / PUBLISHING / PUBLISHED
- FAILED_RETRYABLE / FAILED_PROVIDER / FAILED_QC / FAILED_PERMANENT / CANCELLED

Invalid transitions are rejected.

### 2.2 Provider reliability foundation
M2/M6 reliability primitives already exist:
- retry classification
- exponential backoff + jitter
- rate limiting
- concurrency limits
- quota controls
- circuit breakers
- provider health
- fallback routing
- idempotency abstraction
- cost tracking abstraction

The provider executor measures latency and captures provider cost.

### 2.3 Durable production data model
The database already contains production-oriented tables for:
- runs
- stage executions
- approvals
- publications
- publication attempts
- provider health
- system events
- cost events
- performance snapshots
- production feature snapshots
- experiments
- experiment assignments/outcomes
- optimization decisions

This means M14 can harden existing contracts instead of redesigning the system.

### 2.4 M10–M13 safety chain
M13 explicitly protects:
`ExperimentAnalysis → OptimizationPolicy → OptimizationDecision → Production Adapter → Generation Input`

M14 must preserve this chain.

## 3. Findings

| ID | Severity | Finding | M14 action |
|---|---|---|---|
| M14-A01 | HIGH | Reliability executor's idempotency store is process-local memory | Persist critical idempotency/publication keys durably |
| M14-A02 | HIGH | CostTracker is process-local and does not persist CostEventModel records | Persist per-run/per-stage provider cost |
| M14-A03 | HIGH | ReliabilityTelemetry is process-local and is not wired to SystemEventModel | Persist structured reliability events |
| M14-A04 | HIGH | YouTubePublisher uses its own direct HTTP path instead of the provider reliability executor | Put publication under explicit retry/timeout/error/idempotency controls |
| M14-A05 | HIGH | YouTube upload reads the complete video into memory for the upload request | Use bounded/resumable upload handling |
| M14-A06 | HIGH | Telegram worker catches errors and sends raw exception text to the admin | Sanitize operational errors; keep sensitive/provider details out of Telegram |
| M14-A07 | MEDIUM | Telegram worker offset is process-local | Make update processing replay-safe and durable enough for restart |
| M14-A08 | MEDIUM | Approval/publication operations need stronger concurrent replay protection | Add transactional/idempotent control-plane guards |
| M14-A09 | MEDIUM | Stage/run observability exists in schema but needs consistent lifecycle instrumentation | Guarantee stage start/success/failure/retry events |
| M14-A10 | MEDIUM | Production configuration and health endpoints are minimal | Add explicit operational health/readiness checks |
| M14-A11 | MEDIUM | CI validates static/tests/migration/Docker but not a production-shaped E2E control path | Add deterministic E2E verification with fakes |
| M14-A12 | MEDIUM | README is still M0 bootstrap documentation | Replace with V1 operational documentation |
| M14-A13 | LOW | `.env.example` contains duplicated Telegram keys and development defaults | Normalize production configuration documentation |
| M14-A14 | LOW | Render worker currently runs Telegram polling while Docker default runs webhook | Standardize the supported production deployment mode |

## 4. Important non-findings

The audit does **not** recommend:
- removing human Telegram approval;
- allowing experiments to mutate production automatically;
- bypassing M10 ProductionDecision;
- bypassing M11 TopicSelectionDecision;
- removing M13 rollback;
- coupling optimization to a provider;
- adding paid API calls to CI tests.

These are protected invariants.

## 5. M14 implementation order

### M14.1 — Reliability finalization
1. Durable idempotency/publication guards
2. Provider error normalization
3. Publication retry/recovery semantics
4. Telegram replay/concurrency protection
5. No unknown terminal state

### M14.2 — Observability
1. Run lifecycle instrumentation
2. Stage execution instrumentation
3. Structured SystemEvent persistence
4. Provider latency/success/failure telemetry
5. Correlation through run_id/request_id

### M14.3 — Cost and resource controls
1. Persist CostEvent records
2. Aggregate actual run cost
3. Track provider usage
4. Track estimated vs actual cost
5. Define operational cost reporting

### M14.4 — Security and operational hardening
1. Secret-safe logging
2. Production configuration validation
3. Telegram webhook authentication
4. readiness/health checks
5. deployment mode consistency

### M14.5 — End-to-end verification
Deterministic fake-provider E2E:
`Topic → Script → Visual → TTS → Render → QC → Approval → Publish`

Then production-shaped control verification:
`Publication → Performance Memory → Experiment → Optimization Decision`

Real paid API calls remain outside CI.

### M14.6 — Documentation and release
Deliver:
- final README
- architecture document
- deployment guide
- configuration reference
- operations/runbook
- troubleshooting guide
- provider/reliability reference
- M14 Exit Audit
- V1 release marker

## 6. M14 exit invariants

1. Every production run has a durable run identifier.
2. Every stage has a deterministic lifecycle and terminal outcome.
3. Retryable failures are distinguishable from permanent failures.
4. Publication cannot be duplicated by replay.
5. Approval cannot be replayed into a different state.
6. Provider failures are observable and attributable.
7. Cost is persisted per production run.
8. Secrets never appear in operational messages/logs.
9. M10/M11/M12/M13 safety boundaries remain intact.
10. Human approval remains the publication safety gate.
11. CI uses deterministic fakes and does not consume paid provider APIs.
12. A production-shaped E2E path is demonstrably verifiable.
13. Documentation matches the actual deployment architecture.

## 7. M14.0 decision

**Result: PASS WITH REQUIRED HARDENING**

The repository is structurally ready for M14 implementation. No architectural reset is required.

The highest-priority production gaps are durable reliability state, publication safety, persisted observability/cost, and deployment-operational consistency.

**Next stage:** M14.1 — Reliability Finalization.
