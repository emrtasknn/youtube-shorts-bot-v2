from decimal import Decimal
from uuid import uuid4

from app.application.services.production_decision_adapter import ProductionDecisionAdapter
from app.domain.decision import ProductionDecision


def test_adapter_preserves_legacy_defaults_without_decision() -> None:
    adapter = ProductionDecisionAdapter()

    assert adapter.angle is None
    assert adapter.duration_target_seconds is None
    assert adapter.production_strategy is None
    assert adapter.script_constraints() == "Target 25-40 seconds."


def test_adapter_maps_controlled_decision_to_generation_inputs() -> None:
    decision = ProductionDecision(
        decision_id=uuid4(),
        policy_version="m10-v1",
        angle="curiosity gap",
        duration_target_seconds=Decimal("35"),
        production_strategy="custom_single_vertical_slice",
    )
    adapter = ProductionDecisionAdapter(decision)

    assert adapter.angle == "curiosity gap"
    assert adapter.duration_target_seconds == Decimal("35")
    assert adapter.production_strategy == "custom_single_vertical_slice"
    assert adapter.script_constraints() == (
        "Use this content angle: curiosity gap. "
        "Target approximately 35 seconds."
    )


def test_adapter_uses_only_present_decision_dimensions() -> None:
    decision = ProductionDecision(
        decision_id=__import__("uuid").uuid4(),
        policy_version="m10-v1",
        angle="contradiction",
    )

    assert ProductionDecisionAdapter(decision).script_constraints() == (
        "Use this content angle: contradiction."
    )
