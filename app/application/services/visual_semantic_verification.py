from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class VisualVerificationDecision(StrEnum):
    """Decision produced after checking whether an asset depicts the intent."""

    ACCEPT = "accept"
    ACCEPT_DEGRADED = "accept_degraded"
    UNCERTAIN = "uncertain"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class VisualSemanticScore:
    """Structured semantic evidence for one candidate asset.

    Scores describe what the verifier can establish about the candidate.
    They are deliberately independent from M17 relevance and M19 visual quality.
    """

    entity_match: float
    action_match: float
    context_match: float
    must_show_match: float
    must_avoid_compliance: float
    overall: float

    def __post_init__(self) -> None:
        values = (
            self.entity_match,
            self.action_match,
            self.context_match,
            self.must_show_match,
            self.must_avoid_compliance,
            self.overall,
        )
        if any(not 0.0 <= value <= 1.0 for value in values):
            raise ValueError("Visual semantic scores must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class VisualVerificationPolicy:
    """Thresholds used to turn semantic evidence into a safe decision."""

    accept_threshold: float = 0.78
    degraded_threshold: float = 0.60
    uncertainty_threshold: float = 0.45

    def __post_init__(self) -> None:
        values = (
            self.accept_threshold,
            self.degraded_threshold,
            self.uncertainty_threshold,
        )
        if any(not 0.0 <= value <= 1.0 for value in values):
            raise ValueError("Verification thresholds must be between 0 and 1")
        if not (
            self.accept_threshold
            > self.degraded_threshold
            > self.uncertainty_threshold
        ):
            raise ValueError("Verification thresholds must be strictly descending")

    def decide(self, score: VisualSemanticScore) -> VisualVerificationDecision:
        if score.overall >= self.accept_threshold:
            return VisualVerificationDecision.ACCEPT
        if score.overall >= self.degraded_threshold:
            return VisualVerificationDecision.ACCEPT_DEGRADED
        if score.overall >= self.uncertainty_threshold:
            return VisualVerificationDecision.UNCERTAIN
        return VisualVerificationDecision.REJECT


@dataclass(frozen=True, slots=True)
class VisualVerificationResult:
    """Auditable M20 result for one retrieved visual candidate."""

    decision: VisualVerificationDecision
    score: VisualSemanticScore
    verifier: str
    matched_signals: tuple[str, ...] = ()
    missing_signals: tuple[str, ...] = ()
    violated_constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.verifier.strip():
            raise ValueError("verifier is required")

        for field_name, values in (
            ("matched_signals", self.matched_signals),
            ("missing_signals", self.missing_signals),
            ("violated_constraints", self.violated_constraints),
        ):
            if any(not value.strip() for value in values):
                raise ValueError(f"{field_name} cannot contain empty signals")

    @property
    def accepted(self) -> bool:
        return self.decision in {
            VisualVerificationDecision.ACCEPT,
            VisualVerificationDecision.ACCEPT_DEGRADED,
        }

    @property
    def requires_retry(self) -> bool:
        return self.decision == VisualVerificationDecision.REJECT
