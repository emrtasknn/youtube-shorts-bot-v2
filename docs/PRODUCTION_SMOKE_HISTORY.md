# Production Smoke History

## Workflow
.github/workflows/production-smoke.yml is a manual workflow accepting topic and language. It provisions PostgreSQL, installs FFmpeg, runs migrations, executes the real custom-short command, verifies an MP4 and uploads the artifact. It does not publish.

## Smoke #1
Groq HTTP 400 after Gemini fallback.
PR #122 corrected the request/model configuration, token mapping, temperature setting, reasoning flag and error reporting.

## Smoke #2
Gemini returned truncated structured JSON.
PR #124 increased max output tokens to 6000 and lowered thinking.

## Smoke #3
ffprobe was missing.
PR #125 installed FFmpeg and verified both ffmpeg and ffprobe.

## Smoke #4
Content completeness failed because storyboard vocabulary coverage was too low.
Root cause: lexical overlap was being used as a generic semantic proxy.
PR #126 removed that brittle gate and added a paraphrase regression fixture.

## Post-fix video baseline
Approximately 33.6 seconds, 1080x1920, H.264/AAC, subtitles present, no obvious black/empty frames, visual pacing active.

Quality observations:
- some visuals were relevant but not ideal
- some visuals were held too long
- M20 is metadata-based rather than pixel-level
- first two narrative sentences can repeat the same claim

## Policy
For every major visual milestone:
1. CI must be green.
2. Production smoke must run.
3. The actual MP4 must be inspected.
4. Failures and product-quality observations must be documented.
5. Confirmed findings feed the next milestone.

CI green is not a substitute for MP4 inspection.
