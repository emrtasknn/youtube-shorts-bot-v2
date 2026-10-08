# M29 Exit Audit — Visual–Narration Synchronization

## Scope
M29 establishes one authoritative temporal contract between narration, visual beats, subtitles and M28 camera motion.

## Contract
- VisualBeat remains the storyboard/source timing contract.
- Actual TTS duration is authoritative at render time.
- Scene durations are allocated against actual audio duration.
- Beat durations are proportionally reconciled within each scene.
- Major scene drift is detected automatically and blocks synchronization.
- Subtitle cues are generated against the same total audio duration and validated against the visual timeline.
- Render inputs carry scene index, beat index and source VisualBeatTimeline.
- FFmpeg consumes synchronized beat durations, so M28 motion duration follows the same final beat timing.
- Synchronization metadata is returned in VideoRenderResult and persisted in render-stage audit metadata.

## Runtime flow
VisualBeatTimeline
→ actual audio duration
→ SceneTimingAllocator
→ VisualNarrationSynchronizer
→ UnifiedTimeline
→ synchronized beat durations
→ FFmpeg render
→ subtitles / camera motion / concat
→ VideoQualityGate

## Drift policy
- Default major drift threshold: 2.0 seconds OR 25% of planned scene duration.
- Minor drift is reconciled proportionally.
- Major drift produces an error issue and prevents final synchronized render.
- Timeline end must equal actual audio duration.

## Validation
- contiguous scene and beat timing
- major drift detection
- minor drift reconciliation
- subtitle cue coverage
- invalid duration contracts
- flatten/render-duration helpers
- FFmpeg integration with synchronized beat durations
- mismatched render beat/timeline rejection
- fallback visual scenes receive a valid timeline
- synchronization metadata persistence

## Exit evidence
PR #134.
Final branch workflow run #809: Static checks, Database/tests and Docker build all passed.
Database/tests result: 443 passed.
No database migration or provider/API change was introduced.

Production validation caveat:
Production MP4 smoke/visual inspection was not performed because the available GitHub workflow does not expose a production-smoke dispatch path. This is intentionally not marked complete.
