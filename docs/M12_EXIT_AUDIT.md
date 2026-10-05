# M12 Exit Audit — Controlled Experimentation

**Status:** PASS / COMPLETE  
**Exit date:** 2026-10-05  
**Main SHA at exit:** 842e253fd869efbbe850b0c9ad7b1cf7fbd41eed

## 1. Scope

M12 adds a controlled experimentation layer without allowing experiment results to silently mutate production behavior.

The completed boundary is:

`Experiment → deterministic assignment → outcome evidence → gated analysis → explicit production adapter → generation input`

Experiment results remain evidence/recommendations. They do not become production policy automatically.

## 2. Implemented phases

### M12.1 — Experiment contracts
Implemented immutable domain contracts for:
- Experiment
- ExperimentVariant
- ExperimentAssignment
- ExperimentOutcome
- ExperimentAnalysis
- experiment lifecycle/status and supported dimensions

Supported dimensions:
- TOPIC
- ANGLE
- DURATION_TARGET_SECONDS

### M12.2 — Deterministic assignment and analysis
Implemented:
- stable assignment from `experiment_id + run_key`
- deterministic assignment IDs
- ACTIVE-only assignment
- deterministic winner selection
- weighted average views
- minimum-sample gating

Hardening rule:
- analysis is not ready until **every variant** reaches the configured minimum sample size.

### M12.3 — Persistence and audit
Implemented:
- experiment persistence
- assignment persistence
- outcome persistence
- migration `0009_m12_experimentation`
- idempotent writes
- conflict detection for reused experiment/assignment/outcome identifiers
- persisted outcome rehydration with the corresponding experiment variant

### M12.4 — Controlled production integration
`GenerateCustomShort` can consume an **explicit** experiment variant and assignment.

Rules:
- variant and assignment must be supplied together
- assignment variant must match the supplied variant
- assignment is persisted idempotently
- topic experiment cannot override a selected M11 TopicSelectionDecision
- angle experiment cannot override an explicit M10 ProductionDecision angle
- duration experiment cannot override an explicit M10 ProductionDecision duration
- experiment angle/duration are used only as explicit generation inputs
- production strategy remains controlled by M10
- no provider is selected or mutated by the experiment layer

### M12.5 — Safety boundary
The experimentation layer does not:
- publish autonomously
- remove Telegram/human approval
- mutate ProductionDecision policy automatically
- mutate provider configuration automatically
- introduce provider-specific logic
- introduce ML training
- introduce an autonomous A/B scheduler

## 3. Acceptance criteria

| ID | Criterion | Result |
|---|---|---|
| AC1 | Immutable experiment/variant/assignment/outcome/analysis contracts | PASS |
| AC2 | Deterministic and stable variant assignment | PASS |
| AC3 | Inactive experiments cannot receive assignments | PASS |
| AC4 | Analysis requires minimum samples for every variant | PASS |
| AC5 | Winner selection is deterministic and explainable | PASS |
| AC6 | Persistence is idempotent and conflict-safe | PASS |
| AC7 | Experiment inputs cross an explicit production adapter boundary | PASS |
| AC8 | M10 ProductionDecision safety cannot be bypassed | PASS |
| AC9 | M11 TopicSelectionDecision cannot be silently bypassed | PASS |
| AC10 | Experimentation cannot autonomously publish or mutate production policy | PASS |
| AC11 | Regression/failure coverage exists for assignment, analysis, integration and persistence | PASS |
| AC12 | Database migration, tests, static checks and Docker build are CI-green | PASS |

## 4. Verification

### CI #464
Validated the initial M12 experimentation foundation:
- Ruff check: PASS
- Ruff format: PASS
- mypy: PASS
- database migration: PASS
- pytest: PASS
- Docker build: PASS

### CI #475
Validated the controlled production integration:
- Ruff check: PASS
- Ruff format: PASS
- mypy: PASS
- database migration: PASS
- pytest: PASS
- Docker build: PASS

### CI #483
Final M12 hardening verification:
- Ruff check: PASS
- Ruff format: PASS
- mypy: PASS
- database migration: PASS
- **297 tests passed**
- Docker build: PASS

## 5. Merged PRs

- PR #71 — M12 controlled experimentation foundation
  - merge SHA: `10a346e8f8f426996f7885094f5cab6c550ab8d5`
- PR #72 — controlled experiment integration into generation
  - merge SHA: `38afc91d51ff0899a31a824f9fd12d42fcb7cd1f`
- PR #74 — experiment audit integrity hardening
  - merge SHA: `842e253fd869efbbe850b0c9ad7b1cf7fbd41eed`

PR #73 was intentionally closed and superseded by PR #74 so the final hardening changes were based on the latest green main branch.

## 6. Safety conclusion

M12 establishes experimentation as an **evidence-producing and explicitly consumable layer**, not as an uncontrolled optimization loop.

The following invariant is preserved:

`Experiment result ≠ automatic production policy`

A future optimization stage must explicitly decide when and how an experiment result becomes production policy.

## 7. M13 entry guardrails

M13 may build on:
- experiment definitions
- deterministic assignments
- persisted outcomes
- experiment analyses
- M9 recommendations
- M10 ProductionDecision
- M11 TopicSelectionDecision
- Performance Memory

M13 must not:
- bypass M10 safety
- bypass M11 topic selection safety
- convert experiment winners into permanent policy without an auditable decision
- remove human approval
- introduce uncontrolled autonomous publishing
- couple optimization logic directly to a provider

**M12 exit decision: PASS.**

**Next stage:** M13 — controlled automated optimization/policy stage.
