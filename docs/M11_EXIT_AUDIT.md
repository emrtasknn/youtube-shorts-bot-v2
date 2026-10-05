# M11 Exit Audit — Topic Optimization

## Status

**M11 — COMPLETED**

Audit scope: deterministic topic optimization from candidate set through bounded production integration, including persistence and failure/regression hardening.

Final merge:
- PR #70 — test(m11): harden topic selection regression boundary
- Merge SHA: 08d670bb31e7d625fb2ee509c6e528389ff9f6bf
- CI #451: successful

## M11 Acceptance Criteria

| AC | Criterion | Result | Evidence |
|---|---|---|---|
| AC1 | Topic optimization contract is explicit and domain-safe | PASS | app/domain/topic_optimization.py |
| AC2 | Topic scoring is deterministic, bounded, explainable and cold-start safe | PASS | app/application/services/topic_scoring.py |
| AC3 | Topic selection uses a deterministic bounded policy | PASS | app/application/services/topic_selection.py |
| AC4 | Topic selection decisions are persisted idempotently with audit data | PASS | TopicSelectionDecisionModel, TopicSelectionPersistenceService, migration 0008_m11_topic_select_decisions |
| AC5 | Production consumes an audited topic decision through an explicit adapter | PASS | TopicSelectionProductionAdapter |
| AC6 | Selected topic can override manual topic; no-selection/missing decision preserve fallback behavior | PASS | tests/unit/test_topic_selection_production_adapter.py |
| AC7 | Topic selection does not bypass M10 ProductionDecision safety | PASS | tests/unit/test_m11_topic_selection_regression.py |
| AC8 | Stale decisions, recommendation reuse and rollback remain protected | PASS | M10 safety + M11 regression coverage |
| AC9 | Topic optimization remains provider-agnostic and does not autonomously publish | PASS | No provider/publishing mutation introduced |
| AC10 | Regression/static/database CI is green | PASS | CI #451 successful |

## Deterministic Scoring Boundary

M11.2 uses fixed weights:
- relevance: 0.30
- novelty: 0.30
- trend: 0.15
- evergreen: 0.10
- historical performance: 0.15

Historical performance is used only when comparable observations exist. Missing signals do not create a cold-start penalty; available weights are normalized.

Scores are bounded and rounded to four decimal places.

## Selection Boundary

M11.3 uses a minimum score threshold of 0.60.

Winner ordering:
1. highest total score
2. novelty evidence tie-break
3. deterministic candidate UUID tie-break

No eligible candidate produces a safe NO_SELECTION decision.

## Persistence / Audit Boundary

M11.4 persists:
- decision ID
- status
- selected candidate/topic
- candidate IDs
- selected score and evidence
- rationale
- creation timestamp

Decision IDs are deterministic and persistence is idempotent.

## Production Boundary

TopicSelectionDecision → TopicSelectionProductionAdapter → Generation Input

The topic decision does not directly mutate providers, media selection, TTS, rendering, or publication.

M10 remains independently responsible for:
- angle
- duration target
- production strategy
- recommendation safety
- stale-policy protection
- recommendation reuse protection
- rollback

## Failure / Regression Boundary

M11.6 verifies:
- selected topic and M10 decision compose without cross-mutation
- no-selection preserves manual topic behavior
- stale M10 decisions remain rejected
- rollback removes M10 overrides
- topic selection cannot bypass recommendation reuse protection

CI #451 passed after resolving the regression fixture contract and format checks.

## Explicit Non-Goals

M11 does not introduce:
- A/B experimentation
- ML model training
- automatic provider optimization
- automatic TTS/visual optimization
- autonomous publishing
- removal of Telegram/human approval
- uncontrolled topic generation
- scheduler expansion

## M11 Exit Decision

M11 satisfies its defined boundary and acceptance criteria.

**M11 is closed.**

The next development stage is M12 — Experimentation.

M12 must preserve the M11 guarantees: deterministic auditability where applicable, bounded decisions, human approval, provider abstraction, M10 decision safety, reversible behavior, and regression-safe CI.

## M12 Entry Guardrails

M12 may build on:
- topic selection decisions
- topic scores/evidence
- production decisions
- recommendation history
- performance memory

M12 must not:
- bypass ProductionDecision safety
- directly mutate providers from learning recommendations
- remove human approval
- introduce uncontrolled autonomous publishing
- make experimentation indistinguishable from production policy without explicit auditability
