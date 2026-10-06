# V2 Roadmap — Creative Intelligence & Retention

**Status:** PLANNED  
**Baseline:** V1 complete through M15  
**Primary objective:** move from a reliable Short generator to a reliable system that produces visually specific, fast-moving, evidence-traceable Shorts.

## 1. V2 product thesis

V1 answers:

> Can the system reliably generate, review, and publish a Short?

V2 answers:

> Can the system consistently choose and arrange visuals that make the narration easier to understand and harder to scroll past?

The main quality gap is no longer infrastructure. It is **creative decision quality**.

## 2. V2 success definition

A V2 Short should satisfy all of these:

- the opening visual supports the hook
- concrete entities named in narration are visually represented when feasible
- visual assets match the scene's era/location/action
- generic stock is used only when specific evidence is unavailable
- weak candidates are rejected rather than silently accepted
- visual changes follow semantic beats, not an arbitrary timer
- subtitles emphasize important words without reducing readability
- visual decisions are traceable after generation
- the system can measure why an asset was selected
- post-publication performance can be joined to those decisions
- no V2 feature bypasses V1 reliability or approval invariants

## 3. Milestone plan

### M16 — Visual Intelligence Foundation

**Goal:** turn each scene into a machine-readable visual intent.

Deliver:

- VisualIntent model
- entity/action/location/era extraction from existing SceneContract
- visual beat type
- source priority
- must-show / must-avoid normalization
- visual confidence
- deterministic intent validation
- persisted visual-plan metadata

Exit:

- every production scene has a validated visual intent
- no scene reaches retrieval with an empty visual objective
- existing V1 generation remains compatible
- unit + integration tests green

### M17 — Evidence-Aware Asset Retrieval

**Goal:** stop selecting visually attractive but semantically wrong assets.

Deliver:

- multi-strategy retrieval
- exact entity query
- event query
- era/location query
- broader fallback query
- candidate evidence record
- entity-match score
- action-match score
- era/location score
- query coverage
- source quality score
- duplicate/reuse penalty
- must-avoid hard rejection
- minimum confidence gate

Important rule:

**No eligible candidate → bounded fallback or generation failure. Never silently accept a poor asset.**

Exit:

- selected asset has traceable score breakdown
- exact entity assets outrank generic assets when available
- historical/entity mismatch regressions are covered by tests
- provider costs remain bounded

### M18 — Semantic Visual Pacing

**Goal:** increase visual information density without creating chaotic editing.

Deliver:

- narration beat segmentation
- visual beat boundaries
- scene split/merge policy
- minimum/max visual duration
- image motion policy
- video clip trimming policy
- hook-specific first 1.5–2.0 second treatment
- semantic transition rules

Initial target:

- 5–9 meaningful visual beats for a typical 15–30 second Short
- no arbitrary “change every N seconds” rule
- each beat must have a reason

Exit:

- beat timing is deterministic and testable
- every visual transition maps to a narration/semantic change
- no single static asset dominates the full Short unless intentionally justified

### M19 — Creative QA Gate

**Goal:** detect the failures a human viewer notices before Telegram approval.

Deliver:

- visual-narration mismatch gate
- low-diversity gate
- stale/repeated asset gate
- weak-hook visual gate
- subtitle density/readability checks
- scene-to-audio alignment checks
- creative quality score
- structured failure reasons
- bounded repair path

Repair policy:

1. repair plan
2. one bounded rerender
3. second failure terminates generation

No infinite creative retries.

Exit:

- known V1 smoke failures become automated regressions
- weak visual candidates are rejected before approval
- creative QA is persisted per run

### M20 — Performance Learning Loop

**Goal:** connect visual decisions to real channel performance without autonomous production mutation.

Deliver:

- visual decision telemetry
- asset-level performance joins
- hook/beat/pacing features
- retention proxy features
- YouTube performance ingestion
- cohort analysis
- experiment dimensions for visual decisions
- M12/M13-compatible optimization proposals

Guardrails:

- minimum sample size
- comparable control
- confidence threshold
- explicit policy version
- reversible promotion
- no automatic permanent mutation

Exit:

- a visual experiment can produce evidence
- M13 can evaluate a supported visual dimension
- production policy remains human/policy controlled

### M21 — V2 Production Release

**Goal:** release V2 as a measurable, quality-gated production system.

Deliver:

- V2 production configuration
- full E2E path
- cost budget verification
- reliability verification
- creative QA verification
- rollback documentation
- V2 final exit audit
- 10–20 real Shorts baseline dataset

Exit:

- V1 invariants intact
- V2 creative gates pass
- real-channel smoke passes
- baseline quality improves versus V1
- no material increase in provider failure/cost without measured benefit

## 4. Priority order

| Priority | Milestone | Why |
|---|---|---|
| P0 | M16 | creates the correct semantic contract |
| P0 | M17 | fixes the largest observed quality problem |
| P1 | M18 | improves retention through visual pacing |
| P1 | M19 | prevents bad creative output from reaching approval |
| P2 | M20 | turns production data into controlled learning |
| P2 | M21 | release and prove V2 |

## 5. V2 design constraints

### Reliability

All external providers remain behind existing provider/reliability boundaries.

### Cost

No per-scene LLM call by default.

Preferred order:

1. existing structured scene data
2. deterministic compiler/scoring
3. bounded provider retrieval
4. LLM only when a missing semantic decision materially improves quality

### Explainability

Every selected asset must answer:

- what was searched?
- what candidates were considered?
- why was this asset selected?
- what constraints did it satisfy?
- what constraints did it miss?
- why were alternatives rejected?

### Reversibility

V2 must be feature-flagged or strategy-selectable so V1-compatible generation can be restored without code rollback.

## 6. V2 quality targets

Initial targets are engineering targets, not guaranteed YouTube outcomes:

- visual relevance score: ≥ 0.80 on high-specificity scenes
- must-show fulfillment: ≥ 90% where an eligible source exists
- generic fallback rate: ≤ 20%
- repeated asset rate: ≤ 10%
- visual beat count: 5–9 for 15–30 second videos
- creative QA hard-failure escape rate: 0
- bounded creative repair: ≤ 1 rerender
- no default increase in LLM calls per Short
- no uncontrolled increase in provider spend

These metrics must be calibrated against the first 10–20 V2 runs before becoming hard production thresholds.

## 7. Definition of done for V2

V2 is not complete because the code works.

V2 is complete when:

1. creative decisions are explicit
2. weak decisions are rejected
3. decisions are measurable
4. real outputs improve
5. improvements are reproducible
6. the reliability/control-plane architecture remains intact
