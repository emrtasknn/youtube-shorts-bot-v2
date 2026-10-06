# M14 Final Exit Audit

**Project:** youtube-shorts-bot-v2  
**Milestone:** M14 — Production Hardening & V1 Release  
**Decision:** **PASS — V1 COMPLETE**  
**Exit date:** 2026-10-06

## 1. Executive decision

M14 is complete. The repository has moved from a feature-complete pipeline to a production-hardened V1 baseline with durable reliability state, persistent operational telemetry, cost tracking and budget controls, resumable YouTube publication, Telegram replay protection, deterministic production-shaped E2E coverage, sanitized operational errors, and production deployment documentation.

Human Telegram approval remains mandatory. M10–M13 optimization safety boundaries remain intact.

## 2. M14 scope and outcome

| Area | Final status |
|---|---|
| Production readiness audit | PASS |
| Telegram replay protection | PASS |
| YouTube resumable publication | PASS |
| Durable provider idempotency | PASS |
| Runtime idempotency wiring | PASS |
| Concurrent idempotency write safety | PASS |
| Persistent provider cost events | PASS |
| Persisted run budget guard | PASS |
| Persistent reliability telemetry | PASS |
| Telegram error sanitization | PASS |
| Production-shaped reliability E2E | PASS |
| CI / migration / Docker verification | PASS |
| README / deployment / configuration docs | PASS |
| Final V1 exit audit | PASS |

## 3. Reliability hardening delivered

### Durable idempotency

Provider idempotency is persisted in PostgreSQL through provider_idempotency.

Guarantees:

- survives process restart
- TTL/expiry is enforced
- unique idempotency key
- concurrent duplicate writes are race-safe
- first committed result remains authoritative
- production runtime uses the DB-backed store when a DB session exists

### Telegram replay protection

Telegram update IDs are persisted in telegram_update_receipts.

Guarantees:

- duplicate updates are ignored
- concurrent receipt claims are protected by the database uniqueness constraint
- failed handlers release their receipt so legitimate retries remain possible

### YouTube publication

Publication now uses a dedicated resumable reliability state machine.

Persisted publication state includes:

- upload session URL
- bytes uploaded
- total bytes
- attempt number
- publication status
- retryable/permanent failure state

The implementation streams video data instead of loading the full video into memory.

### Cost persistence and budget control

Provider cost records are persisted in cost_events.

The runtime now:

- records provider cost with run metadata
- survives process restart
- exposes durable spend to operations
- checks persisted RunModel.budget_target
- blocks subsequent provider calls after a run budget is exhausted
- emits a provider.budget_exhausted reliability event

### Reliability telemetry

Provider reliability events are persisted in system_events.

Instrumented events include:

- provider.idempotency_hit
- provider.success
- provider.error
- provider.exhausted
- provider.budget_exhausted

Telemetry persistence failures are isolated so observability does not become a new single point of failure for the provider path.

## 4. Security and operational hardening

Telegram operational errors no longer send raw exception text to the administrator.

Instead, the admin receives a generic actionable message while detailed exceptions remain in application logs.

Production configuration was normalized:

- duplicate Telegram variables removed from .env.example
- Render configuration now declares the provider configuration required by the Telegram worker
- real secrets remain platform-managed
- CI contains no paid API execution path

## 5. Control-plane invariants preserved

1. Human Telegram approval remains mandatory before publishing.
2. Experiments do not autonomously mutate production policy.
3. M10 production decisions remain protected.
4. M11 topic-selection safety remains protected.
5. M13 optimization policy gates remain mandatory.
6. M13 rollback remains available.
7. Optimization is not coupled to a provider.
8. No autonomous publishing was introduced.

## 6. Production-shaped E2E

A deterministic PostgreSQL-backed E2E test now verifies the complete reliability path with a fake provider:

1. provider request executes
2. result is persisted to durable idempotency storage
3. cost is persisted
4. reliability success telemetry is persisted
5. the same request is executed again
6. provider is not called a second time
7. idempotency-hit telemetry is persisted
8. only one cost event and one idempotency record exist

The test uses no paid external APIs.

## 7. Verification

Final M14 CI verification reached:

**325 passed in 3.34s**

The final verified CI gate also passed:

- Ruff check
- Ruff format check
- MyPy
- Alembic upgrade
- PostgreSQL-backed pytest
- Docker build

Key verified milestone runs included:

- #526 — durable idempotency runtime wiring — PASS
- #528 — concurrent idempotency write hardening — PASS
- #537 — persistent reliability telemetry — PASS
- #545 — Telegram operational hardening — PASS
- #550 — production-shaped reliability E2E — PASS
- #554 — persisted run budget controls — PASS

## 8. M14 merge chain

| PR | Scope | Result |
|---:|---|---|
| #80 | Production readiness audit | MERGED |
| #81 | Telegram replay protection | MERGED |
| #82 | YouTube publication reliability | MERGED |
| #83 | Durable provider idempotency | MERGED |
| #84 | Durable idempotency runtime wiring | MERGED |
| #85 | Concurrent idempotency hardening | MERGED |
| #86 | Persistent cost events | MERGED |
| #88 | Persistent reliability telemetry | MERGED |
| #90 | Telegram error sanitization | MERGED |
| #92 | Production-shaped reliability E2E | MERGED |
| #93 | Persisted run budget controls | MERGED |

## 9. Accepted architecture exceptions

### Publication reliability is intentionally specialized

YouTube publication does not use the generic provider executor directly.

This is an intentional architecture boundary rather than an accidental reliability gap: publication has a distinct external side effect, resumable upload protocol, persisted upload session, publication attempt state, and unknown-outcome handling.

The generic provider executor remains the reliability boundary for generation providers. Publication retains its specialized state machine to avoid layering two independent retry systems around the same external side effect.

### Telegram polling offset remains process-local

The worker's polling offset is not treated as the source of truth. Durable Telegram update receipts provide the actual replay protection, so restart/replay behavior remains safe.

## 10. Deployment checklist

Before enabling continuous production operation:

- configure production PostgreSQL
- run alembic upgrade head
- configure Telegram credentials and admin IDs
- configure YouTube OAuth credentials
- configure enabled provider API keys
- configure Render environment variables
- verify YouTube privacy setting
- send a test generation to Telegram
- verify human approval
- verify publication state and YouTube URL
- verify system_events, cost_events, provider_idempotency, and publication attempt records

## 11. V1 operating rule

M14 marks the end of the planned V1 engineering milestone chain.

The correct next step is operation and measurement, not another reliability milestone by default.

Recommended V2 work should be driven by real production evidence:

- channel performance
- provider failure rates
- cost per published Short
- approval/rejection/regeneration rates
- publication failure rates
- experiment sample sizes
- optimization rollback frequency
- operational burden

## 12. Final conclusion

**M0–M14 is complete. V1 is production-ready within the documented operating boundaries.**

The system now has durable state at the critical reliability boundaries, deterministic replay protection, resumable publication, persistent cost and telemetry data, budget enforcement, human-controlled publishing, protected optimization, CI-backed verification, and an operational documentation baseline.

**M14 EXIT: PASS / COMPLETE.**
