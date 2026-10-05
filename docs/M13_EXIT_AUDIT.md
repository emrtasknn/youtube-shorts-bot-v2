# M13 Exit Audit — Controlled Automated Optimization

**Status:** PASS / COMPLETE  
**Exit date:** 2026-10-05  
**Main SHA at implementation exit:** 40e264a47e2dd65a597acdb1e4dae5f09cce4aba

## 1. Source basis

The master plan places M11–M14 in the production-hardening phase and requires reliability, cost, observability, security, scale and quality to remain controlled. M12 explicitly establishes the experimentation layer as evidence-producing rather than an uncontrolled optimization loop.

M13 therefore implements the missing policy boundary:

`ExperimentAnalysis → OptimizationPolicy Gate → OptimizationDecision → Production Adapter → Generation Input`

## 2. M13 implementation

### M13.0 — Repository audit
Completed before feature implementation.

The audit confirmed:
- M9 recommendations already exist.
- M10 ProductionDecision is the protected production decision layer.
- M11 TopicSelectionDecision is the protected topic-selection layer.
- M12 ExperimentAnalysis provides deterministic, minimum-sample-gated evidence.
- No auditable mechanism existed to promote experiment evidence into bounded optimization policy.

Audit document:
`docs/M13_OPTIMIZATION_POLICY_AUDIT.md`

### M13.1 — Optimization policy contract
Added:
- `OptimizationPolicy`
- `OptimizationDecision`
- `OptimizationDecisionStatus`

Promotion requires:
- ready experiment analysis
- comparable control performance
- minimum uplift
- minimum confidence
- supported experiment dimension
- explicit policy version

Default policy:
- minimum uplift: **10%**
- minimum confidence: **HIGH**

Confidence follows the project's deterministic evidence bands:
- 0: INSUFFICIENT
- 3–5: LOW
- 6–14: MEDIUM
- 15+: HIGH

### M13.2 — Deterministic promotion gate
Implemented:
- winner-vs-control weighted average view comparison
- deterministic uplift calculation
- confidence gate
- deterministic decision ID
- explainable rationale
- safe NO_PROMOTION outcome when evidence is insufficient

A winning experiment therefore does **not** automatically become production policy merely because it has a winner.

### M13.3 — Persistence / audit
Added:
- `optimization_decisions` database table
- migration `0010_m13_optimization_decisions`
- idempotent decision persistence
- conflicting-record rejection
- complete audit fields

### M13.4 — Production integration
`GenerateCustomShort` now accepts an explicit `OptimizationDecision`.

The production adapter:
- ignores NO_PROMOTION decisions
- rejects stale policy versions
- converts PROMOTED decisions into bounded generation inputs
- protects M10 angle/duration decisions
- protects M11 topic decisions
- contains no provider-specific logic

### M13.5 — Reversibility
Added explicit rollback support.

Rollback:
- does not mutate the original decision
- creates a distinct ROLLED_BACK decision
- preserves experiment provenance
- is rejected by the production adapter as a non-PROMOTED state

### M13.6 — Failure/regression hardening
Coverage includes:
- below-uplift rejection
- insufficient confidence rejection
- not-ready analysis rejection
- deterministic decision IDs
- M10 conflict
- M11 conflict
- stale policy rejection
- NO_PROMOTION behavior
- rollback behavior
- persistence conflict safety

## 3. Acceptance criteria

| ID | Criterion | Result |
|---|---|---|
| AC1 | Experiment evidence can be evaluated by an explicit immutable optimization policy | PASS |
| AC2 | Promotion requires a comparable control | PASS |
| AC3 | Promotion requires minimum uplift | PASS |
| AC4 | Promotion requires sufficient confidence | PASS |
| AC5 | Promotion decision is deterministic and explainable | PASS |
| AC6 | Optimization decisions are persisted and auditable | PASS |
| AC7 | Production consumes optimization only through an explicit adapter | PASS |
| AC8 | M10 ProductionDecision cannot be silently overridden | PASS |
| AC9 | M11 TopicSelectionDecision cannot be silently overridden | PASS |
| AC10 | Stale optimization policy is rejected | PASS |
| AC11 | Optimization is explicitly reversible | PASS |
| AC12 | NO_PROMOTION cannot affect generation | PASS |
| AC13 | No provider-specific or autonomous publishing logic was introduced | PASS |
| AC14 | CI, migration, tests, static checks and Docker are green | PASS |

## 4. Verification

### M13 PR #76 — CI #497
Final foundation verification:
- Ruff check: PASS
- Ruff format: PASS
- mypy: PASS
- Alembic migration: PASS
- **308 tests passed**
- Docker build: PASS

### M13 PR #77 — CI #502
Final safety verification:
- Ruff check: PASS
- Ruff format: PASS
- mypy: PASS
- Alembic migration: PASS
- **310 tests passed**
- Docker build: PASS

## 5. Merged implementation PRs

- PR #76 — controlled optimization policy layer
  - merged
  - main merge SHA: `2cbd312ab5ad3e80d518784d359b193fd9208703`
- PR #77 — rollback and safety hardening
  - merged
  - main merge SHA: `40e264a47e2dd65a597acdb1e4dae5f09cce4aba`

## 6. Critical invariant

M13 establishes:

`Experiment winner ≠ automatic permanent production policy`

The system now has a controlled promotion mechanism, but promotion still requires:
1. explicit policy,
2. minimum evidence,
3. control comparison,
4. auditable decision,
5. protected production adapter.

Human approval and the existing publication safety chain remain untouched.

## 7. M14 entry guardrails

M14 may build on:
- M9 recommendations
- M10 ProductionDecision
- M11 TopicSelectionDecision
- M12 experiments and outcomes
- M13 OptimizationDecision
- performance memory

M14 must not:
- bypass optimization policy gates
- silently overwrite an active optimization decision
- remove rollback capability
- bypass M10/M11 safety
- couple optimization to a specific provider
- introduce autonomous publishing without a separately audited control-plane decision
- consume paid APIs in unit/integration/CI tests

**M13 exit decision: PASS.**

**Next stage:** M14 — production hardening, observability, cost, reliability and scale controls.
