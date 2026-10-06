# M15 — Autonomous Audio Intelligence

## Objective

Upgrade the Shorts audio pipeline from voiceover plus an optional manually supplied background track to one autonomous, quality-gated audio mix per video.

The default production path must remain token-conscious. M15 does not render two full audio variants for every video.

## Cost rule

Default flow:

1. one existing script-generation call
2. zero additional LLM calls for audio planning
3. one TTS generation
4. autonomous music/SFX selection from a curated catalog
5. one FFmpeg render
6. one audio QC pass
7. bounded repair/rerender only when QC fails

A/B audio variants are experimental only and should use the existing M12/M13 experimentation and optimization controls after enough production evidence exists.

## M15 phases

### M15.1 — Voice Direction + TTS Hardening
- deterministic AudioDirector
- normalized narration boundaries
- compact emphasis metadata
- preserve the existing TTS provider abstraction
- audio duration/silence/clipping QC
- provider retry/fallback remains controlled by the existing reliability layer

### M15.2 — Music Intelligence
- curated/licensed music catalog abstraction
- mood, energy, BPM, instrumentation and vocal flags
- topic/script-derived music profile
- deterministic ranking and selection
- explicit source/license metadata
- no claim that any track is inherently viral

### M15.3 — SFX Intelligence
- semantic event extraction from existing scene/script data
- curated SFX catalog
- deterministic event-to-SFX matching
- density and overlap limits
- no SFX when confidence is low

### M15.4 — Dynamic Audio Mixer
Reuse the existing FFmpeg renderer and ducking implementation.
Add voice priority, music automation, SFX ducking, intro/transition/outro fades, and controlled impact boosts.

### M15.5 — Audio QC + Autonomous Repair
Gate the video before Telegram review:
- integrated loudness
- peak/clipping
- voice/music balance
- silence ratio
- duration alignment
- SFX density/overlap
- deterministic repair policy

A failed QC should produce a bounded repair attempt, never an open-ended loop.

### M15.6 — Production Measurement
Persist enough audio metadata to answer:
- which audio profile was used?
- which music/SFX assets were selected?
- did QC require repair?
- what did retention look like afterward?

Use M12/M13 for controlled audio experiments rather than generating variants by default.

## Exit criteria

M15 is complete only when:

- one normal run produces one autonomous audio mix
- no extra LLM call is required for audio planning
- music selection is deterministic, licensed/traceable, and catalog-backed
- SFX selection is deterministic and density-limited
- voice always has priority over music/SFX
- audio QC is a hard gate before approval
- bounded autonomous repair works for recoverable audio failures
- telemetry can connect audio profile to later experiment outcomes
- all unit/integration/CI tests remain green
- paid API calls are not introduced into CI tests

## Current implementation slice

M15.1 starts with a zero-token AudioDirector. It is provider-agnostic and does not change the Fish Audio API contract. Its emphasis metadata is intentionally advisory until a provider explicitly supports prosody controls.
