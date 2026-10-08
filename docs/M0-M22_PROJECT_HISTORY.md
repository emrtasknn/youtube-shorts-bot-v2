# M0–M22 Project History

## Purpose
Historical handoff for the current V2 production baseline. GitHub main is the implementation source of truth.

## Milestones
M0–M5 DONE — core production, approval, publishing, pilot.
M6 DONE — production intelligence.
M7 DONE — analytics/performance snapshots.
M8 DONE — performance memory/query/baseline/data quality.
M9 DONE — learning signals and recommendations.
M10 DONE — controlled decision integration.
M11 DONE — content intelligence.
M12 DONE — experimentation.
M13 DONE — automated optimization.
M14 DONE — production hardening.
M17 DONE — evidence-aware visual retrieval.
M18 DONE — visual pacing.
M19 DONE — visual quality gate.
M20 DONE — semantic visual verification.
M21 DONE — production hardening for the visual pipeline.
M22 DONE — production smoke.

M15–M16 are historical transition work and are not active future milestones.

## M17
Evidence-aware retrieval was restored/hardened. VisualCandidateSelector supports beautifiable candidates and retrieval became evidence-driven rather than a blind single lookup.

## M18
Introduced VisualBeat, VisualBeatTimeline and VisualBeatCompiler. Beats preserve Scene Contract semantics and allocate timing from narration. Production integration maps beats into render inputs.

## M19
Introduced Visual Quality Gate with composition, resolution, portrait suitability, cleanliness and beautifiability signals. Decisions are ACCEPT, BEAUTIFY, ACCEPT_DEGRADED and REJECT. The evaluator is not pixel-level vision.

## M20
Introduced VisualVerificationDecision: ACCEPT, ACCEPT_DEGRADED, UNCERTAIN, REJECT. Result carries decision, score, verifier, matched_signals, missing_signals and violated_constraints.

Current verifier is deterministic-metadata-v1 and searches candidate metadata such as alt, description, title and tags. It does NOT inspect pixels.

## M21
Added failure containment, retrieval audit trace, persisted retrieval attempts and verifier failover. A valid primary UNCERTAIN or REJECT decision is authoritative; fallback is for provider errors/unavailability.

## M22
Added manual production smoke workflow at .github/workflows/production-smoke.yml. It provisions PostgreSQL, installs FFmpeg, runs migrations, executes the real custom-short command, verifies the MP4 and uploads the artifact. It does not publish to YouTube.

### Smoke #1
Groq HTTP 400 after Gemini fallback.
Fix: corrected request/model configuration, mapped maxOutputTokens to max_completion_tokens, removed temperature 0, added include_reasoning false and improved error reporting. PR #122.

### Smoke #2
Gemini structured JSON was truncated.
Fix: maxOutputTokens 6000 and low thinking. PR #124.

### Smoke #3
ffprobe missing on GitHub runner.
Fix: install FFmpeg and verify ffmpeg/ffprobe. PR #125.

### Smoke #4
ScriptCompletenessGate rejected valid paraphrased storyboard narration because of brittle lexical vocabulary coverage.
Fix: removed the generic lexical coverage gate and added a regression fixture. PR #126.

### Video baseline
A real video was subsequently generated at roughly 33.6 seconds, 1080x1920, H.264/AAC, with subtitles and working visual pacing. Observations: some visuals were relevant but not ideal, some were held too long, M20 is not pixel-level, and the first two narrative sentences can repeat the same claim.

## Current pipeline
Topic → Script generation → parse/normalize → Scene Contract → Script Completeness Gate → VisualBeat compilation → M17 retrieval → M19 quality → M20 semantic verification → M21 reliability/audit → TTS/audio → render → QC → Telegram approval → YouTube publish.

## Lessons
1. Production smoke catches integration failures that unit tests miss.
2. HTTP success does not mean usable provider output.
3. Structured LLM output needs token-budget protection.
4. Runtime binaries are part of the production contract.
5. Lexical overlap is not a safe substitute for semantic understanding.
6. Every quality gate needs regression fixtures.
7. CI green is necessary but does not prove video quality.
8. Audit traces are required to explain asset decisions.
