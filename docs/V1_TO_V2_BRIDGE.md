# V1 → V2 Bridge

**Project:** youtube-shorts-bot-v2  
**Baseline:** V1 production-ready  
**Current main:** `b09a644cad6d9bc7f19b12f3e954eb9fa4545e41`  
**Bridge date:** 2026-10-06

## 1. V1 completion state

M0–M15 are complete.

V1 established:

- provider abstraction and reliability core
- deterministic idempotency and persistent reliability telemetry
- Telegram human approval control plane
- resumable YouTube publication
- M10–M13 controlled experimentation and optimization
- content completeness gates
- narration-driven deterministic scene timing
- M15 autonomous audio intelligence
- CI, PostgreSQL migration checks, Docker verification
- production deployment documentation

V1 is not being replaced. V2 is an intelligence and creative-quality layer on top of the existing reliability boundary.

## 2. Latest production evidence

The first successful post-M15 smoke reached Telegram after the deterministic scene-timing fix.

The generated video was reviewed from a real-viewer perspective.

Observed strengths:

- hook is understandable and curiosity-driven
- narration/audio is production-usable
- subtitles are readable
- story structure is coherent
- render is technically clean
- Telegram review path is functioning

Observed weaknesses:

1. **Visual-narration mismatch**
   - a narration referring to Al Jolson / The Jazz Singer can receive a generic singer visual.
2. **Generic stock feel**
   - visual assets can communicate an era or mood without proving the exact event/person/entity.
3. **Low visual beat density**
   - several seconds can be represented by one static asset.
4. **Weak historical authenticity**
   - generic stock imagery competes with the value of factual historical material.
5. **Limited visual progression**
   - scene transitions are driven mainly by the storyboard rather than by semantic changes in narration.
6. **Subtitle emphasis is still mostly static**
   - readable, but not yet strongly kinetic or hook-aware.

These are V2 priorities.

## 3. Architectural principle

Do not solve V2 by weakening existing gates.

The correct sequence is:

**improve upstream intent → retrieve better candidates → score candidates with evidence → reject weak candidates → render → measure → learn**

Existing reliability, idempotency, budget, approval, and optimization boundaries remain mandatory.

## 4. V2 non-goals

V2 does not initially:

- remove human approval
- introduce autonomous publishing
- create default A/B render variants
- add an LLM call for every scene unless evidence justifies it
- replace the existing provider reliability layer
- replace M12/M13 experimentation
- treat a visual relevance score as proof of factual correctness

## 5. Current extension points

The current generation pipeline already contains:

- `SceneContract`
- `VisualRelevanceContext`
- `VisualSourceResolver`
- `StockMediaScorer`
- `StockMediaSelector`
- `SearchStockMedia`

V2 should evolve these components rather than build a parallel media pipeline.

## 6. Target V2 flow

```text
Script
  ↓
Scene Contract
  ↓
Visual Intent Compiler
  ↓
Visual Plan
  ├─ entity
  ├─ action
  ├─ era/location
  ├─ must-show
  ├─ must-avoid
  ├─ visual beat
  └─ source priority
  ↓
Candidate Retrieval
  ↓
Evidence-aware Candidate Scoring
  ↓
Asset Selection / bounded fallback
  ↓
Visual QA
  ↓
Edit Plan
  ↓
Render
  ↓
Creative QA + technical QC
  ↓
Telegram approval
  ↓
YouTube publication
  ↓
Performance telemetry
  ↓
M12/M13 controlled learning
```

## 7. Immediate next action

Before implementing V2 features, rerun the latest production smoke and preserve:

- run ID
- generated script
- scene contracts
- selected asset IDs
- visual scores/reasons
- render duration
- audio QC
- video QC
- Telegram approval result
- final YouTube URL when published

That run becomes the V2 baseline sample.
