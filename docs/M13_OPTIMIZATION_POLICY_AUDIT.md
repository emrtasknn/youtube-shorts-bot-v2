# M13 Repository Audit — Controlled Automated Optimization

**Baseline:** main `0900517ca01498e36dbb071c64ef7cc757fa6740`  
**Status:** audit complete; implementation boundary defined.

## Source basis

The master plan defines M11–M14 as production hardening and requires reliability, cost, observability, security, scale and quality to remain controlled. M12's exit audit explicitly states that M13 may build on experiment analyses, M9 recommendations, M10 ProductionDecision, M11 TopicSelectionDecision and Performance Memory, but must not bypass M10/M11 safety or turn experiment winners into permanent policy without an auditable decision.

## Current state

M9 produces recommendations. M10 converts eligible recommendations into an auditable ProductionDecision. M11 produces an auditable TopicSelectionDecision. M12 produces deterministic experiment assignments, persisted outcomes and gated analyses and exposes explicit experiment production overrides.

## M13 gap

There is currently no domain contract that answers:

**When is experiment evidence strong enough to become a bounded production optimization policy?**

There is also no persistence/audit record for such a promotion decision and no explicit generation boundary for an optimization decision.

## M13 boundary

`ExperimentAnalysis + Experiment definition → Policy Promotion Gate → OptimizationDecision → Production Adapter → Generation Input`

The promotion gate will require:
- analysis ready
- every variant at minimum sample
- explicit control variant
- minimum uplift over control
- minimum confidence derived from sample size
- deterministic winner
- supported production dimension
- policy version

The resulting decision will be:
- immutable
- auditable
- deterministic
- reversible
- conflict-safe
- provider-agnostic

## Explicit non-goals

- no provider routing
- no autonomous publishing
- no removal of human approval
- no ML training
- no scheduler expansion
- no silent mutation of M10 ProductionDecision
- no silent bypass of M11 TopicSelectionDecision
- no permanent policy mutation without a persisted decision
