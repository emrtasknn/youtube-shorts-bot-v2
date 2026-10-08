# Project Rules & Architectural Decisions

## Source-of-truth hierarchy
1. GitHub main — implementation truth.
2. Tests/CI — executable behavior contract.
3. Architecture/decision docs — intended architecture and rationale.
4. History/handoff docs — historical context.

## Core rules
1. Reliability first.
2. Core logic is provider agnostic.
3. Telegram human approval remains the publication control point.
4. Prefer deterministic checks before adding LLM calls.
5. Semantic correctness beats visual variety.
6. Quality gates must be conservative and avoid false rejection.
7. Fallback is bounded and must not override valid primary decisions.
8. Important retrieval, quality, semantic, retry and fallback decisions must be traceable.
9. CI green is necessary but not sufficient.
10. Production policy changes must be observable and reversible.

## M23
Narrative redundancy is a real product defect. First implementation should conservatively detect exact duplicates, very high lexical similarity, hook/first-body repetition and adjacent sentence repetition. Do not recreate the removed vocabulary coverage gate under another name. Prompt-level narrative progression is also required.

## M24
Retrieval moves toward Scene Contract → Query Expansion → Candidate Pool → Quality → Semantic Verification → Ranking → Best Candidate. Expensive verification is applied to shortlisted candidates.

## M25
Real pixel-level vision implements the existing semantic verifier contract. It does not bypass the normalized decision/result model.

## M26
Variety is a ranking signal. Exact duplicates can be hard rejected where alternatives exist, but semantic relevance always wins.

## M27
Caption segmentation/timing is a separate module from rendering. Renderer consumes timed caption segments.

## M28
Camera motion is selected from scene purpose, composition, duration and recent motion, not uncontrolled randomness. Static fallback remains.

## M29
VisualBeat becomes the unified temporal contract for narration, visual, caption and motion. Drift must be detectable.

## M30
Final video evaluation is multidimensional: technical, narrative, visual, audio, captions, synchronization and product quality. Decisions: PASS, PASS_WITH_WARNINGS, RETRY, REJECT.

## Non-goals
Do not silently expand M23–M30 into autonomous publishing, arbitrary new social networks, web dashboard, SaaS billing, long-form video or unrestricted trend crawling.

## Development loop
Plan → Contract → Implementation → Unit tests → Integration tests → Failure tests → CI → Production smoke → MP4 inspection → Audit → Merge.
