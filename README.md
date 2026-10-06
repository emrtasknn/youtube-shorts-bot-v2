# youtube-shorts-bot-v2

Production-oriented, provider-agnostic modular monolith for automated YouTube Shorts generation, human approval, publishing, analytics, and controlled optimization.

## Current release state

**M0–M14: COMPLETE — V1 production hardening complete.**

The V1 pipeline keeps human approval as a mandatory control-plane gate. M10–M13 optimization decisions remain evidence-driven and reversible; experiments do not autonomously change production policy or publish content.

## Architecture

The runtime is organized around:

- **Generation pipeline:** topic → script → scenes/visuals → TTS → render → QC
- **Control plane:** Telegram review → approve/reject/regenerate → publish
- **Reliability core:** retry classification, rate limiting, concurrency limits, quota controls, circuit breakers, fallback routing, durable idempotency, durable cost events, persistent reliability telemetry
- **Publishing:** YouTube OAuth + resumable uploads with persisted upload state and bounded retry behavior
- **Intelligence:** performance memory → experiments → OptimizationPolicy → controlled production adapter → generation input
- **Operations:** PostgreSQL, SQLAlchemy/Alembic, Docker, Render worker, GitHub Actions

## Safety invariants

The following are intentional V1 boundaries:

1. YouTube publishing requires the Telegram human approval path.
2. Duplicate Telegram updates are DB-protected.
3. Duplicate provider requests are DB-protected with a unique idempotency key.
4. YouTube uploads persist resumable session state and uploaded bytes.
5. Experiment winners do not automatically become permanent production policy.
6. M13 optimization decisions are policy-gated and reversible.
7. Paid provider APIs are not called by CI tests.
8. Provider failure must not expose raw operational exceptions to Telegram admins.
9. Run budget exhaustion blocks subsequent provider calls when a persisted budget_target is configured.

## Local development

Requirements: Python 3.12, Docker, and PostgreSQL.

~~~bash
python -m venv .venv
pip install -e ".[dev]"
cp .env.example .env
docker compose up -d postgres
alembic upgrade head
pytest -q
~~~

Enable repository hooks:

~~~bash
pre-commit install
pre-commit run --all-files
~~~

## Runtime commands

Generate a custom Short:

~~~bash
python -m app custom "Your topic"
~~~

Send pending approvals to Telegram:

~~~bash
python -m app telegram-review
~~~

Run the Telegram approval/publishing worker:

~~~bash
python -m app telegram-poll
~~~

Run the webhook server:

~~~bash
python -m app telegram-webhook
~~~

## Production deployment

Render is configured as a Docker worker. The worker startup command runs migrations before starting the Telegram polling worker:

~~~text
alembic upgrade head && python -m app telegram-poll
~~~

Production secrets must be supplied through the deployment platform; do not commit .env or real API credentials.

For the production configuration contract, failure handling, rollback rules, and M14 acceptance criteria, see:

- docs/M14_PRODUCTION_READINESS_AUDIT.md
- docs/M14_FINAL_EXIT_AUDIT.md
- docs/M13_EXIT_AUDIT.md

## CI quality gate

Every production change is expected to pass:

- Ruff lint
- Ruff format check
- MyPy
- Alembic migration upgrade
- PostgreSQL-backed pytest suite
- Docker build

The M14 exit verification reached **325 passing tests** with migration and Docker checks green.

## Troubleshooting

### Migration failure

Run:

~~~bash
alembic upgrade head
~~~

Check the current revision:

~~~bash
alembic current
~~~

### Provider failure

Inspect persisted system_events, provider health state, and the run/stage records before retrying. Do not bypass the reliability layer or manually mutate optimization policy.

### Duplicate generation

Check the provider idempotency key and provider_idempotency table. A duplicate key should resolve to the first committed provider result.

### Telegram replay

Telegram updates are claimed through telegram_update_receipts. Replayed updates are ignored. If a handler fails, its receipt is released so the operation can be retried.

### YouTube upload interruption

Publication attempts persist the resumable upload session URL and byte offset. A retry should resume the upload when the session remains valid; a lost session is treated as an unknown outcome rather than blindly creating another publication.

## M14 final status

See docs/M14_FINAL_EXIT_AUDIT.md for the final V1 production-readiness decision and remaining non-blocking follow-up items.
