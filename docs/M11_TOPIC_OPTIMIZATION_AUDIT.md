# M11.0 — Topic Optimization Audit

## Status

M11.0 is an audit-only boundary definition. It does not change production behavior.

M10 is complete. The current learning-to-production boundary is:

```
Performance Memory
    ↓
Feature Extraction
    ↓
Learning Evidence / Confidence
    ↓
Recommendation
    ↓
Decision Policy
    ↓
ProductionDecision
    ↓
Generation Input
```

M11 extends learning upstream toward topic selection, but must preserve the M10 controlled decision boundary.

## Repository findings

### 1. Topic data model already exists

The M1 schema already contains `topic_candidates` with:

- source
- title
- angle
- relevance_score
- novelty_score
- trend_score
- evergreen_score
- status

The lifecycle is:

`NEW → EVALUATING → ACCEPTED / REJECTED → USED`

Therefore M11 should activate and formalize an existing domain concept rather than introduce a parallel topic model.

### 2. Content already stores the selected topic

`ContentModel` contains:

- topic
- angle
- category
- language
- novelty_score
- status

The current custom generation vertical slice accepts a topic directly through `CustomShortRequest`. M11 must not break this manual/custom path.

### 3. Topic selection service is currently missing

The repository contains the topic persistence schema and topic lifecycle enum, but there is no dedicated topic candidate repository/service/scoring use case in the current application tree.

The existing `GenerateCustomShort` flow does not select a topic. It receives one.

Therefore the main M11 implementation gap is:

```
Candidate Topics
      ↓
Topic Evaluation
      ↓
Topic Selection
```

### 4. Learning currently observes topic but does not optimize it

`LearningFeature` includes `TOPIC`, and performance memory stores the published topic.

However, the current M10 `DecisionPolicyEngine` intentionally maps only:

- angle → ANGLE
- duration_bucket → DURATION_TARGET_SECONDS

Topic recommendations are not production dimensions in M10.

This is intentional and must remain true until M11 defines a bounded topic-selection contract.

### 5. Performance baselines are currently production-cohort based

Performance memory is keyed around stable production features including:

- category
- language
- topic
- angle
- duration
- production strategy
- hook
- visual providers
- TTS provider

The current baseline service builds baselines by category/language/platform and matches production strategy.

M11 must avoid treating raw topic performance as directly comparable when cohorts are materially different.

## M11 problem definition

M11 should answer:

> Given a set of valid topic candidates, which candidate should be preferred based on deterministic evidence, novelty, historical performance, and bounded policy?

It should not yet answer:

> Which provider, model, TTS, visual strategy, or experiment should be used?

Those remain outside the M11 boundary.

## Proposed M11 boundary

```
Topic Candidate Set
        ↓
Eligibility / Data Quality
        ↓
Topic Evidence
        ↓
Topic Score
        ↓
Topic Selection Decision
        ↓
ProductionDecision / Generation Input
```

The exact integration contract will be defined in M11.1 before implementation.

## Required M11 constraints

1. **Deterministic**
   - Same candidate/evidence input must produce the same selection.

2. **Bounded**
   - Topic optimization may select among supplied candidates.
   - It must not silently create arbitrary topics.

3. **Explainable**
   - Selection must expose score components and rationale.

4. **Novelty-aware**
   - Existing novelty/event-memory safeguards must remain authoritative.

5. **Performance-aware**
   - Historical performance may influence selection only when evidence is comparable and sufficiently mature.

6. **Cold-start safe**
   - Topics with insufficient history must not be treated as proven winners.

7. **Manual-mode safe**
   - Existing custom/manual generation remains unchanged.

8. **M10-compatible**
   - M11 must not bypass `ProductionDecision` or inject raw recommendations directly into generation.

9. **Provider-agnostic**
   - Topic selection must not depend on Gemini, TTS, stock-media, or other concrete providers.

10. **Regression-safe**
   - Existing generation, M9 learning, and M10 decision behavior must remain valid.

## Known implementation gaps

M11 still needs explicit contracts for:

- TopicCandidate domain model
- candidate repository/query boundary
- topic evidence model
- scoring dimensions and weights
- minimum evidence rules
- cold-start behavior
- tie-breaking
- selection decision/audit model
- integration point with production generation
- persistence and idempotency
- failure/regression tests

## M11 implementation sequence

### M11.1 — Topic optimization contract
Define immutable topic candidate, evidence, score, and selection contracts.

### M11.2 — Deterministic topic scoring
Implement bounded scoring from candidate metadata and eligible historical evidence.

### M11.3 — Topic selection policy
Implement eligibility, cold-start handling, confidence requirements, and deterministic tie-breaking.

### M11.4 — Persistence / audit
Persist the selected topic decision and its evidence/rationale.

### M11.5 — Production integration
Connect the selected topic to the existing generation path without changing the manual/custom contract.

### M11.6 — Failure / regression coverage
Cover insufficient data, conflicting evidence, duplicate candidates, stale decisions, novelty rejection, and legacy generation behavior.

### M11.7 — Exit audit
Verify M11 acceptance criteria and define the M12 experimentation boundary.

## M11 non-goals

M11 will not implement:

- automatic A/B experimentation
- ML model training
- provider optimization
- TTS optimization
- visual provider optimization
- autonomous publishing
- automatic removal of human approval
- uncontrolled topic generation
- scheduler/batch expansion

## Entry boundary

M11 starts from the existing persisted topic candidate schema and M9/M10 learning infrastructure.

The intended architecture is:

```
Topic Candidates
       +
Performance Memory
       +
Novelty / Content Memory
       ↓
M11 Topic Optimization
       ↓
Bounded Topic Selection
       ↓
M10 Production Decision Boundary
       ↓
Generation
```

No implementation is included in M11.0 beyond this audit document.
