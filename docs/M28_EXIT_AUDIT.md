# M28 Exit Audit — Dynamic Camera Motion

## Scope
M28 adds controlled, deterministic camera motion to still visual assets in the custom Shorts rendering path.

## Contract
- Motion is represented by a typed `CameraMotionPlan`.
- Supported motions: push-in, pull-out, pan left/right/up/down, and static.
- Motion intensity is bounded to a maximum 10% zoom delta.
- Focus coordinates are normalized to 0..1.
- Beats shorter than 1.25 seconds use a static fallback.
- Recent motion types are deprioritized to avoid repetitive camera behavior.
- Motion is applied only to still-image scenes; existing video inputs remain unchanged.

## Runtime flow
Scene/VisualBeat
→ CameraMotionEngine
→ CameraMotionPlan
→ VideoSceneInput.motion
→ FFmpeg zoompan
→ existing concat/audio/subtitle pipeline
→ VideoQualityGate

## Tests
- Camera motion determinism and bounds
- short-beat static fallback
- recent-motion de-prioritization
- invalid input/plan rejection
- render adapter motion propagation
- FFmpeg zoompan command contract
- static-image fallback without motion
- invalid motion contract rejection

## Operational boundaries
- No new provider/API calls.
- No database migration.
- Existing M24/M25/M26 visual selection semantics are unchanged.
- Motion never outranks semantic visual correctness because it is applied only after visual selection.
- Production MP4 smoke/visual inspection must only be marked complete when an actual production workflow run and video inspection are available.

## Exit evidence
PR #133.
Branch CI evidence: workflow run #803 (Static checks, Database/tests, Docker build all successful). PR #133. Main merge commit: `4d8258a12af3534c2e214f99c5fb8f020a8cd4ea`. Main CI run #806 passed Static checks, Database/tests and Docker build.

Production validation caveat: no production MP4 smoke/visual inspection was performed because the available GitHub workflow does not expose a production-smoke dispatch path. This is not represented as completed validation.
