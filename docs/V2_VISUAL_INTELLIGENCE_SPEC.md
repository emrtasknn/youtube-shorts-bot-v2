# V2 Visual Intelligence Specification

**Status:** Architecture specification  
**Scope:** M16–M19  
**Primary defect addressed:** generic or semantically incorrect visuals

## 1. Current problem

The current V1 pipeline already has:

- scene contracts
- visual queries
- relevance context
- deterministic stock scoring
- provider fallback

The remaining problem is that text overlap is not enough.

A candidate can contain words such as “singer” and “1927” and still be the wrong person or event.

Therefore V2 introduces **evidence-aware visual selection**.

## 2. Visual Intent

Each scene should compile into:

```text
VisualIntent
├── scene_index
├── primary_entity
├── secondary_entities[]
├── action
├── location
├── era
├── event
├── visual_goal
├── must_show[]
├── must_avoid[]
├── source_priority[]
├── beat_type
├── specificity
└── confidence
```

### Beat types

Initial controlled vocabulary:

- HOOK
- PERSON
- PLACE
- EVENT
- OBJECT
- ACTION
- CONSEQUENCE
- PAYOFF
- TRANSITION

The vocabulary should stay small so it remains deterministic and testable.

## 3. Source priority

For high-specificity factual scenes:

1. exact historical/entity source
2. exact event source
3. credible archival/historical visual
4. high-confidence contextual stock
5. generic stock

For generic conceptual scenes:

1. relevant stock video
2. relevant stock photo
3. procedural visual treatment

A lower-priority source must never outrank a higher-priority source solely because it has better aesthetic metadata.

## 4. Candidate evidence

Every candidate should have a normalized evidence object:

```text
CandidateEvidence
├── provider
├── provider_asset_id
├── query_used
├── title
├── description
├── source_url
├── entity_matches[]
├── event_matches[]
├── location_matches[]
├── era_matches[]
├── action_matches[]
├── must_show_matches[]
├── must_avoid_matches[]
├── source_priority
├── duplicate_penalty
├── resolution_score
├── portrait_score
└── total_score
```

If a provider does not expose a field, it is **unknown**, not a positive match.

## 5. Scoring model

Initial deterministic score:

```text
specificity
×
(
  entity      * 0.30
  + event     * 0.20
  + must_show * 0.20
  + action    * 0.10
  + era       * 0.05
  + location  * 0.05
  + query     * 0.05
  + technical * 0.05
)
-
duplicate_penalty
-
must_avoid_penalty
```

This is an initial engineering model, not a permanent formula.

The score must be persisted component-by-component so M20 can determine which signals actually correlate with performance.

## 6. Hard rejection rules

Reject a candidate when:

- a must-avoid term matches
- required entity is contradicted by available metadata
- portrait requirement is not met for a portrait-only scene
- resolution is below production minimum
- provider asset was already used in the same Short when reuse is disallowed
- candidate confidence is below the scene's minimum threshold

Do not “average away” a hard contradiction with a high technical score.

## 7. Retrieval strategy

For a specific scene:

### Strategy A — exact

```text
"The Jazz Singer" "Al Jolson" 1927
```

### Strategy B — entity/event

```text
Al Jolson The Jazz Singer
```

### Strategy C — historical context

```text
1927 Hollywood sound film
```

### Strategy D — broad fallback

```text
silent film theater 1920s
```

The resolver should stop as soon as it has an eligible candidate above the required confidence threshold.

## 8. Visual evidence tiers

Each selected asset gets one tier:

- **A:** exact entity/event evidence
- **B:** strong contextual evidence
- **C:** generic contextual visual
- **D:** emergency fallback

Production should target A/B.

C should be measurable and visible in telemetry.

D should be rare and should trigger a creative-quality warning.

## 9. Semantic pacing

Visual duration is no longer derived only from storyboard duration.

The planner should create:

```text
Narration
→ semantic beats
→ visual beats
→ asset assignments
→ duration allocation
```

Existing narration-driven scene timing remains the timing safety floor.

V2 must preserve the current rule:

> no scene may be shorter than the narration it is responsible for displaying.

## 10. Hook treatment

The first beat receives special treatment.

Required properties:

- immediate semantic relevance
- strongest available source priority
- readable hook subtitle
- no irrelevant establishing shot
- first visual change within a bounded interval when narration changes meaning

The exact interval should be experimentally calibrated rather than hard-coded as a universal YouTube rule.

## 11. Asset diversity

Diversity is not randomization.

A Short should avoid:

- same asset twice
- same visual composition repeatedly
- five consecutive static frames with identical framing
- multiple generic assets for the same factual entity

Diversity should be constrained by semantic continuity.

## 12. Visual QA output

The creative gate should produce:

```text
CreativeVisualReport
├── overall_score
├── scene_reports[]
├── weak_scenes[]
├── missing_entities[]
├── generic_fallbacks[]
├── repeated_assets[]
├── beat_count
├── hook_score
└── repair_recommendation
```

This report is persisted before Telegram approval.

## 13. Compatibility

V2 should extend:

- `VisualRelevanceContext`
- `VisualSourceResolver`
- `StockMediaScorer`
- `StockMediaSelector`
- `SearchStockMedia`

It should not create a second competing asset-selection stack.

## 14. First implementation boundary

M16 should not implement semantic video editing.

M16 only establishes the contract and telemetry.

M17 should prove that the selector can choose a historically specific asset over a generic one.

M18 can then change pacing.

This sequencing prevents three variables from changing simultaneously.
