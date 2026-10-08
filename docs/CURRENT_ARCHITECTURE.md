# Current Architecture — M22 Baseline

## Source of truth
GitHub main is the implementation source of truth. This document is the architectural handoff map.

## Production flow
Topic → GenerateCustomShort → structured script → parse_script → SceneContract → ScriptCompletenessGate → VisualBeatCompiler → M17 retrieval → M19 quality → M20 semantic verification → M21 failure containment/audit → TTS/AudioDirector → FFmpeg renderer → QC → Telegram approval → YouTube publish.

## Scene Contract
Current fields:
- narration
- visual_goal
- visual_query
- purpose
- subject
- action
- entities
- location
- era
- visual_intent
- visual_style
- must_show
- must_avoid

build_scene_contract requires non-empty narration, visual_goal and visual_query.

## Script normalization
custom_short_support.parse_script:
- requires hook, body, duration_target and scenes
- requires 3–6 scenes
- normalizes entities, must_show and must_avoid
- constrains scene duration
- rejects generic-only visual queries

## Script generation
GenerateCustomShort._create_script requests hook, body, CTA, duration target, event memory and structured scenes. Scene data includes duration, narration, visual_goal, visual_query, purpose, subject, action, entities, location, era, visual_intent, visual_style, must_show and must_avoid.

Current Gemini structured generation uses a 6000-token output budget and low thinking to prevent the M22 truncation failure.

## Narrative quality
HookEngine evaluates hook types including shocking fact, unanswered question, impossible event, curiosity gap, contradiction and generic.

Known gap: there is no dedicated narrative redundancy gate yet. This is M23.

## Completeness
ScriptCompletenessGate checks structural completeness: body length, complete sentence, scene count, scene narration coverage, duration, purpose diversity, first-scene hook, final payoff and complete scene narration.

The old generic lexical storyboard vocabulary gate was deliberately removed because it rejected valid paraphrases.

## Visual chain
M17 supplies evidence-aware retrieval.
M18 supplies visual beats and pacing.
M19 supplies visual quality decisions.
M20 supplies semantic verification.
M21 supplies failure containment and audit trace.

## M20 limitation
Current semantic verification is metadata-based, not pixel-level. M25 is reserved for real vision verification.

## Reliability rule
A valid primary verifier decision is authoritative. Fallback is allowed for provider error/unavailability and must not silently override a valid primary UNCERTAIN or REJECT.

## Audio and captions
AudioDirector currently creates TTS from hook + body + CTA. The renderer receives subtitle text as a text payload. Word-level dynamic caption timing is not yet wired in. M27 addresses this.

## Motion
FFmpeg is the rendering dependency. Production smoke installs and verifies ffmpeg and ffprobe. Advanced camera motion is not yet a first-class scene contract. M28 addresses this.

## Observability target
Run → Scene → Query → Candidate → Quality → Semantic → Variety → Selected asset → Beat → Audio → Caption → Motion → Sync → Final Judge.

## Known M23–M30 gaps
1. Narrative redundancy
2. Multi-query retrieval
3. Pixel-level semantic verification
4. Visual variety state
5. Dynamic captions
6. Dynamic camera motion
7. Unified synchronization
8. Automated final video judge

## Documentation rule
When code and documentation disagree, code wins and documentation must be corrected.
