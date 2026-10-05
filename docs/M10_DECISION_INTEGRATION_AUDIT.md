# M10.0 — Controlled Decision Integration Audit

## Status

M10.0 is an audit-only stage.

No production behavior is changed by this document.

## M10 objective

M10 is the first milestone allowed to connect:

```
Recommendation
    ↓
Decision Policy
    ↓
Generation Input
```

The connection must remain controlled, explainable, bounded, auditable, and reversible.

M9 ends at `Recommendation`.

M10 begins at the decision boundary.

## Current production input boundary

The current production vertical slice is `GenerateCustomShort`.

`CustomShortRequest` currently contains:

- `topic`
- `run_key`
- `language`
- `requested_by`
- `output_path`

It does not currently contain a learning recommendation, production decision, angle override, duration override, or production-strategy override.

The current use case creates `RunModel` with:

```
strategy = "custom_single_vertical_slice"
```

This is currently a fixed implementation value.

The script-generation request also embeds production choices directly in the prompt, including:

- target duration
- hook preferences
- scene requirements
- visual query requirements

Therefore M10 should not inject recommendation handling directly into the LLM prompt or scatter recommendation checks throughout the pipeline.

## Existing M9 boundary

M9 already provides:

- `LearningSignal`
- `Recommendation`
- `RecommendationStatus`
- `RecommendationQueryService`
- `LearningRecommendationService`

M9 recommendations are evidence, not production mutations.

M9 recommendation states remain historical and queryable.

## Decision boundary requirement

M10 should introduce one explicit domain/application contract representing the decision that production is allowed to consume.

The conceptual flow should become:

```
Recommendation(s)
        ↓
Decision Policy
        ↓
Production Decision
        ↓
GenerateCustomShort / future production orchestrator
```

The production pipeline must consume the `ProductionDecision`, not raw recommendations.

## Proposed ProductionDecision responsibilities

The contract should represent only bounded production choices that the current pipeline can actually consume.

Initial candidates:

- selected topic
- language
- duration target
- angle
- production strategy
- applied recommendation IDs
- decision rationale
- policy version
- created timestamp

Fields must only be added when they map to an actual downstream input.

M10 must not invent fields for capabilities that do not yet exist.

## Decision policy rules

Initial policy must be deterministic.

A recommendation is eligible only when:

1. status is `GENERATED` or explicitly policy-approved for use;
2. confidence satisfies the configured minimum;
3. direction is POSITIVE or NEGATIVE;
4. delta exists;
5. evidence has a comparable baseline;
6. the recommendation targets a production feature supported by the decision contract;
7. the recommendation does not conflict with a stronger decision already selected.

The first implementation should be conservative.

A recommendation must never override a production input merely because it exists.

## Example

Given:

```
feature = angle
feature_value = "surprising fact"
metric = retention
delta = +0.13
confidence = HIGH
sample_size = 18
direction = POSITIVE
```

the policy may produce:

```
ProductionDecision(
    angle = "surprising fact",
    applied_recommendation_ids = [...]
)
```

The policy should not directly mutate the script generator.

## Negative recommendation handling

Negative recommendations must not be interpreted as destructive commands.

For example:

```
duration_bucket = "50s+"
direction = NEGATIVE
```

should become a bounded decision such as:

```
avoid_preference(duration_bucket="50s+")
```

rather than:

```
force_duration = 20
```

unless a later policy explicitly defines that mapping.

This prevents a recommendation from silently becoming an unsafe production mutation.

## Conflict handling

If multiple recommendations affect the same decision dimension, M10 must define deterministic conflict handling.

Initial rule:

1. filter ineligible recommendations;
2. group by decision dimension;
3. prefer higher confidence;
4. prefer larger absolute delta only when confidence is equal;
5. preserve deterministic recommendation-ID tie breaking;
6. record rejected/conflicting recommendation IDs in the decision rationale.

No last-write-wins behavior should exist.

## Confidence policy

M9 confidence levels remain:

- `INSUFFICIENT`
- `LOW`
- `MEDIUM`
- `HIGH`

Initial M10 default should be conservative:

```
minimum confidence = MEDIUM
```

The threshold must be policy configuration, not hardcoded throughout the production pipeline.

LOW-confidence recommendations remain queryable evidence but do not automatically influence production decisions in the first M10 implementation.

## Rollback requirement

Every applied recommendation must be traceable.

A production decision must therefore retain:

- policy version
- applied recommendation IDs
- rejected/conflicting recommendation IDs where relevant
- decision timestamp
- resulting decision values

Rollback means the production pipeline can fall back to its pre-M10/default inputs without deleting recommendation history.

M10 must not modify or delete M9 recommendation history when a decision is rejected or rolled back.

## Decision logging

M10 must make the decision auditable.

At minimum:

```
decision_id
policy_version
input recommendation IDs
eligible recommendation IDs
applied recommendation IDs
rejected/conflicting recommendation IDs
final decision values
created_at
```

The log must explain **why** a recommendation was or was not applied.

## Production integration boundary

The first production integration should be narrow.

Preferred direction:

```
GenerateCustomShort
    ↓
resolve ProductionDecision
    ↓
create script / scenes using decision inputs
```

The decision resolver should remain replaceable so the future scheduler, topic intelligence, and experimentation layers can consume the same contract.

M10 must not couple the decision policy to:

- a specific LLM provider
- a specific TTS provider
- a specific stock-media provider
- YouTube publishing
- Telegram approval

## M10 proposed sub-phases

### M10.0 — Repository / Decision Audit
**THIS DOCUMENT**

No production behavior change.

### M10.1 — Production Decision Domain Contract
Define the immutable domain contract and policy configuration.

### M10.2 — Decision Policy Engine
Convert eligible recommendations into deterministic bounded decisions.

### M10.3 — Decision Persistence / Audit
Persist decision history and applied recommendation references.

### M10.4 — Production Integration Adapter
Expose the decision to the generation pipeline through one explicit input boundary.

### M10.5 — Rollback / Conflict Handling
Verify deterministic conflict resolution and safe fallback to defaults.

### M10.6 — Regression / Failure Tests
Cover recommendation eligibility, conflicts, low confidence, rollback, and unchanged behavior when no recommendation is applicable.

### M10.7 — Exit Audit
Verify M10 acceptance criteria and prepare M11 entry.

## M10 acceptance criteria

M10 is not DONE until:

### AC1 — Controlled
Recommendations influence production only through the decision policy.

### AC2 — Deterministic
Same recommendations + same inputs + same policy produce the same decision.

### AC3 — Bounded
Only explicitly supported production fields can be changed.

### AC4 — Confidence-aware
Low/insufficient evidence cannot silently mutate production defaults.

### AC5 — Explainable
Every applied decision can identify its recommendation evidence and policy rationale.

### AC6 — Conflict-safe
Conflicting recommendations resolve deterministically.

### AC7 — Reversible
Production can fall back to pre-M10/default behavior without losing learning history.

### AC8 — Non-provider-coupled
Decision policy does not depend on a concrete LLM/TTS/media provider.

### AC9 — Regression-safe
Existing M0–M9 behavior remains valid when no eligible recommendation exists.

### AC10 — CI-green
All M10 changes pass the repository CI suite.

## Explicit non-goals

M10 does not implement:

- autonomous experimentation
- explore/exploit optimization
- automatic topic discovery optimization
- automatic provider switching based on performance
- scheduler/batch orchestration
- TikTok publishing
- ML-based recommendation scoring
- automatic deletion of poor-performing recommendations

Those belong to later milestones.

## M10 entry decision

The repository is ready for M10.1.

The key architectural decision is:

> **Production consumes a deterministic `ProductionDecision` contract, never raw `Recommendation` objects.**

This keeps M9 reusable, M10 controlled, and M11/M12/M13 extensible.
