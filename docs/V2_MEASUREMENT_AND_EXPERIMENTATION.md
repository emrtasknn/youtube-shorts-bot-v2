# V2 Measurement & Experimentation Plan

**Purpose:** determine whether V2 creative decisions improve Shorts rather than merely making code or videos look more sophisticated.

## 1. Measurement layers

### Layer A — generation quality

Measured before approval:

- script completeness
- scene timing validity
- visual intent completeness
- asset relevance
- entity fulfillment
- generic fallback rate
- asset reuse rate
- visual beat count
- hook visual score
- subtitle density
- audio QC
- video QC
- render failures

### Layer B — operational efficiency

- provider calls per Short
- LLM calls per Short
- provider latency
- provider failures
- retries
- cost events
- generation duration
- repair rerenders
- approval rejection rate
- regeneration rate

### Layer C — human approval signal

Telegram actions:

- approved first pass
- rejected
- regenerated
- rejection reason where available
- time to approval

### Layer D — YouTube performance

When available:

- impressions
- views
- viewed vs swiped away
- average view duration
- average percentage viewed
- likes
- comments
- shares
- subscribers gained
- traffic/source signals

Performance data must be linked to the run and content IDs.

## 2. V2 baseline

The first 10–20 Shorts after V2 introduction should be treated as a baseline cohort.

Do not promote optimization rules from one or two videos.

Record at minimum:

- topic
- language
- duration target
- hook type
- scene count
- visual beat count
- visual evidence tiers
- generic fallback rate
- audio profile
- publish timestamp
- performance metrics when available

## 3. Primary V2 hypothesis

**H1:** better visual-narration alignment improves viewer retention.

Operational proxy:

- higher visual relevance
- lower generic fallback
- lower human rejection rate
- improved viewed-vs-swiped-away
- improved average percentage viewed

The proxy does not prove causation.

## 4. Secondary hypotheses

**H2:** higher semantic visual beat density improves retention until a saturation point.

**H3:** exact historical/entity visuals outperform generic stock on factual-history topics.

**H4:** hook-specific visual treatment improves early retention.

**H5:** kinetic subtitle emphasis improves comprehension/retention without increasing subtitle-related rejection.

## 5. Experiment dimensions

Only one major creative dimension should be changed per controlled experiment.

Initial candidates:

- visual evidence tier
- visual beat density
- hook visual treatment
- subtitle emphasis
- asset source strategy
- static image vs motion clip

Do not simultaneously change topic policy, duration policy, audio policy, and visual policy in the same experiment.

## 6. M12/M13 compatibility

V2 experiments must feed the existing experimentation and optimization architecture.

A promotion candidate requires:

- ready experiment analysis
- comparable control
- minimum sample size
- minimum uplift
- HIGH confidence
- supported optimization dimension
- explicit policy version

No direct write from experiment code into permanent production configuration.

## 7. Attribution

Every creative decision should be traceable:

```text
run_id
  → scene_id
    → visual_intent
      → retrieval strategies
        → candidates
          → selected_asset
            → score/evidence
              → render
                → publication
                  → performance
```

This is the core V2 learning loop.

## 8. Decision hierarchy

When metrics conflict:

1. safety / policy
2. factual integrity
3. technical validity
4. narration/visual alignment
5. retention proxy
6. aesthetic preference

A prettier but factually misleading visual is not a V2 win.

## 9. Cost guardrail

V2 should not introduce a hidden multiplicative cost.

Track:

```text
cost_per_generated_short
cost_per_published_short
provider_calls_per_short
llm_calls_per_short
rerenders_per_short
```

Any feature that increases cost materially must have a measurable quality hypothesis.

## 10. V2 release comparison

Before declaring V2 better, compare V1 and V2 cohorts on:

- first-pass approval rate
- regeneration rate
- visual relevance
- generic fallback rate
- provider cost
- generation time
- viewed-vs-swiped-away
- average percentage viewed

Do not compare raw views without accounting for topic and distribution differences.

## 11. Minimum evidence rule

No production optimization decision should be made from:

- one viral video
- one failed video
- a single manual impression
- one unusual topic
- a single metric

Real production evidence must be cohort-based and compatible with M12/M13 controls.
