from __future__ import annotations

from dataclasses import dataclass

from app.domain.decision import ProductionDecision


@dataclass(frozen=True, slots=True)
class ProductionDecisionSafety:
    """Guard production application against stale, conflicting, or irreversible decisions."""

    policy_version: str

    def validate(
        self,
        decision: ProductionDecision,
        *,
        previously_applied_recommendation_ids: tuple[str, ...] = (),
    ) -> None:
        if decision.policy_version != self.policy_version:
            raise ValueError(
                f"Decision policy version '{decision.policy_version}' does not match "
                f"expected '{self.policy_version}'."
            )

        previous = set(previously_applied_recommendation_ids)
        current = {str(item) for item in decision.applied_recommendation_ids}
        conflict = current & previous
        if conflict:
            conflict_ids = ", ".join(sorted(conflict))
            raise ValueError(f"Decision reuses already applied recommendation IDs: {conflict_ids}")

    @staticmethod
    def rollback(*, policy_version: str) -> ProductionDecision:
        """Return a reversible no-override decision without mutating prior audit history."""
        return ProductionDecision.empty(policy_version=policy_version)
