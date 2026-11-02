# Otopilot reliability integration

This integration adapts selected Otopilot engineering patterns to the existing
Python architecture. It does not copy Otopilot's Node.js application wholesale.

## Adopted now

- Atomic final publication: render to a unique sibling staging file and use
  `os.replace` only after the configured video engine returns successfully.
- Preserve a previously validated output when a retry fails.
- Remove abandoned staging files after success or failure.
- Keep the existing FFprobe, synchronization, subtitle, audio and Automated
  Video Judge gates as the source of truth.

## Existing equivalents retained

The bot already has scene/beat contracts, visual candidate scoring and semantic
verification, provider abstraction and retry policies, TTS/audio QC, subtitle
generation, synchronization, video quality gates and a judge-driven retry path.
Replacing these with Otopilot's JavaScript implementations would duplicate
capabilities and introduce a second runtime.

## Deliberately not copied

- Edge TTS as a production fallback: it is not an official stable API.
- Local Piper/VoxCPM runtime: this would add deployment and model/GPU
  requirements that are not currently part of the bot's hosted runtime.
- Otopilot's local desktop panel and local job files: the bot's database,
  Telegram approval flow and GitHub Actions are its operational control plane.
- Otopilot's FFmpeg graph wholesale: the current engine already handles
  synchronized visual beats, voiceover, ducking and burned subtitles.

## Follow-up candidates

1. Per-scene render artifacts with content-addressed cache keys.
2. Persisted stage checkpoints and resumable job orchestration.
3. More granular FFprobe checks (codec, pixel format, audio sample rate and
   stream duration) before approval.
4. An actual provider-backed production run and human review of visual relevance.
