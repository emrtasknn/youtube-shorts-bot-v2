# M9 Exit Audit — Learning Signals & Recommendations

## Status

M9 is complete through the following merged stages:

| Stage | Scope | Status |
| --- | --- | --- |
| M9.0 | Learning audit | DONE |
| M9.1 | Learning domain contracts | DONE |
| M9.2 | Deterministic feature extraction | DONE |
| M9.3 | Evidence and confidence | DONE |
| M9.4 | Recommendation engine | DONE |
| M9.5 | Recommendation persistence | DONE |
| M9.6 | Recommendation query | DONE |
| M9.7 | Learning integration boundary | DONE |
| M9.8 | Tests and regression | DONE |
| M9.9 | Exit audit | THIS DOCUMENT |

## Delivered contract

M9 implements the deterministic pipeline:

```
PerformanceQueryResult
        |
        v
FeatureObservation
        |
        v
LearningSignal
        |
        v
Recommendation
        |
        +--> persistence
        |
        +--> query
```

The integration boundary is implemented by `LearningRecommendationService`.

It composes:

1. `LearningFeatureExtractionService`
2. `LearningEvidenceService`
3. `RecommendationEngine`

The integration boundary materializes input results once and does not mutate production strategy, content, provider selection, or publishing behavior.

## Feature scope

M9 deliberately uses only production features that exist in the current M8 contract:

- `category`
- `angle`
- `duration_bucket`
- `topic`

The current implementation does not invent a `hook_type` abstraction. Raw hook text remains available in production memory but is not treated as a derived hook taxonomy.

Metrics currently evaluated:

- `views`
- `average_view_duration_seconds`
- `retention`

Duration buckets are deterministic:

- `<20s`
- `20-29s`
- `30-39s`
- `40-49s`
- `50s+`

## Evidence and confidence policy

Confidence is deterministic and sample-size based:

- 0–2 observations: `INSUFFICIENT`
- 3–5: `LOW`
- 6–14: `MEDIUM`
- 15+: `HIGH`

A zero data-quality score forces `INSUFFICIENT`.

For non-category features, a baseline is usable only when all contributing publications belong to exactly one M8 baseline cohort:

- category
- language
- production strategy

Mixed cohorts do not produce a fabricated delta.

Category recommendations intentionally do not compare against a category-scoped baseline because that comparison would be semantically meaningless.

## Recommendation policy

A recommendation is generated only when all of the following are true:

- confidence is LOW, MEDIUM, or HIGH
- direction is POSITIVE or NEGATIVE
- delta exists
- comparable baseline evidence exists

Neutral, insufficient, or non-comparable signals are not promoted to recommendations.

Recommendation IDs are deterministic UUID5 values.

Recommendations are created in `GENERATED` state.

M9 does not activate or apply recommendations automatically.

## Persistence

Recommendations are persisted in the `recommendations` table.

The persisted record includes the recommendation plus the relevant signal/evidence snapshot:

- recommendation ID
- signal ID
- feature and feature value
- metric
- observed value
- baseline value
- delta
- sample size
- baseline availability
- data quality score
- evidence notes
- confidence
- direction
- recommendation text
- status
- creation timestamp

Persistence is idempotent on `recommendation_id`.

Migration chain at the M9 exit point:

```
0004_m7_performance_snapshots
        |
        v
0005_m8_prod_feature_snapshot
        |
        v
0006_m9_recommendations
```

## Query boundary

`RecommendationQueryService` supports deterministic reads by:

- recommendation ID
- status
- feature
- metric
- confidence
- direction
- positive limit

List ordering is deterministic:

1. newest `created_at`
2. `recommendation_id` descending as tie-breaker

## Regression coverage

M9.8 locks the generate → persist → query contract.

CI coverage for the completed M9 work includes:

- Ruff check
- Ruff format
- mypy
- Alembic migration upgrade
- pytest
- Docker build

The M9.8 regression test verifies that a generated recommendation can be persisted and reconstructed through the query layer without losing its domain signal contract.

## M9 boundary

M9 ends at:

```
Observe -> Understand -> Recommend
```

M9 does **not**:

- change production strategy automatically
- change provider routing automatically
- change script generation automatically
- change visual selection automatically
- publish content automatically
- run autonomous experiments
- close the learning loop into production

Those responsibilities belong to later milestones.

## M10 entry contract

M10 may consume `Recommendation` objects as decision evidence.

The expected direction is:

```
Recommendation
      |
      v
Controlled Decision Boundary
      |
      v
Explicit production decision
```

The M10 implementation must preserve the M9 rule that recommendations are evidence, not autonomous mutations.

## Known pre-existing technical debt

The following items pre-date the M9 learning layer and remain outside the M9 exit criteria:

1. StockMediaStrategy abstraction mismatch.
2. `tts_provider` is not populated in every desired `PerformanceMemoryService._build_memory` path.
3. Performance snapshot concurrency can still produce an IntegrityError under simultaneous capture.
4. M8.8 contains some query redundancy.
5. Learning feature extraction currently uses the latest available time-series point without a dedicated maturity/horizon policy.

These items should not be silently folded into M10. They should be handled explicitly as technical-debt work or as part of the relevant milestone.

## Exit decision

M9 is considered complete because the system can now:

1. extract deterministic production-feature observations from performance memory;
2. evaluate evidence and confidence;
3. convert actionable signals into explainable recommendations;
4. persist recommendations idempotently;
5. query recommendations deterministically;
6. execute the full learning pipeline without mutating production behavior;
7. regression-test the generate → persist → query contract.

**Next milestone: M10 — Controlled Decision Integration.**
