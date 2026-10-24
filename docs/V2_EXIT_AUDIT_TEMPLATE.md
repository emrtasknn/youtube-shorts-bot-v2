# V2 Final Exit Audit Template

**Project:** youtube-shorts-bot-v2  
**Release:** V2  
**Decision:** PENDING

## 1. Executive decision

V2 may be marked PASS only when:

- all V1 invariants remain intact
- V2 creative gates are active
- real production smoke succeeds
- V2 output quality is measurably better than the V1 baseline
- operational cost remains bounded
- M12/M13 safety boundaries remain intact
- rollback is documented and tested

## 2. Milestone status

| Milestone | Scope | Status |
|---|---|---|
| M16 | Visual Intelligence Foundation | PENDING |
| M17 | Evidence-Aware Asset Retrieval | PENDING |
| M18 | Semantic Visual Pacing | PENDING |
| M19 | Creative QA Gate | PENDING |
| M20 | Performance Learning Loop | PENDING |
| M21 | V2 Production Release | PENDING |

## 3. V1 invariants

- [ ] Telegram human approval remains mandatory
- [ ] YouTube publishing remains resumable
- [ ] provider idempotency remains durable
- [ ] Telegram replay protection remains durable
- [ ] persisted cost/budget controls remain active
- [ ] provider reliability layer remains active
- [ ] M12 experiments remain evidence-producing
- [ ] M13 optimization remains policy-gated and reversible
- [ ] no autonomous permanent production mutation

## 4. Creative quality

- [ ] visual intent exists for every production scene
- [ ] selected assets have evidence records
- [ ] exact entity/event candidates outrank generic candidates when available
- [ ] must-show constraints are enforced
- [ ] must-avoid constraints are enforced
- [ ] visual beat count is controlled
- [ ] hook visual is validated
- [ ] subtitle readability is validated
- [ ] visual diversity is validated
- [ ] creative QA is a hard gate before Telegram approval

## 5. Operational quality

- [ ] no uncontrolled LLM-call multiplication
- [ ] provider costs are persisted
- [ ] generation latency is measured
- [ ] creative repair is bounded
- [ ] no infinite retry loop
- [ ] Docker build passes
- [ ] Alembic upgrade passes
- [ ] full test suite passes
- [ ] static checks pass

## 6. Production evidence

Minimum recommended evidence:

- [ ] 10–20 V2 Shorts generated
- [ ] at least one real Telegram approval flow
- [ ] at least one real YouTube publication
- [ ] visual decision telemetry captured
- [ ] V1/V2 cohort comparison completed
- [ ] rejection/regeneration reasons analyzed

## 7. Release thresholds

Initial targets to calibrate before final hardening:

| Metric | Initial target |
|---|---:|
| High-specificity visual relevance | ≥ 0.80 |
| Must-show fulfillment where source exists | ≥ 90% |
| Generic fallback rate | ≤ 20% |
| Repeated asset rate | ≤ 10% |
| Typical visual beats | 5–9 |
| Creative hard-gate escapes | 0 |
| Creative repair renders | ≤ 1 |
| Unplanned LLM-call increase | 0 |
| Uncontrolled provider cost increase | 0 |

These are release targets, not assumptions about YouTube performance.

## 8. Final verification record

Record:

- final main SHA
- final CI run
- test count
- Docker result
- migration result
- real smoke run ID
- Telegram approval result
- YouTube URL
- V1 cohort size
- V2 cohort size
- key performance deltas
- known exceptions

## 9. Final decision

**V2 EXIT: PENDING**

Do not change this to PASS until the evidence above is recorded.
