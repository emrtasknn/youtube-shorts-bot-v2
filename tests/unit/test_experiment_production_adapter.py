from decimal import Decimal
from uuid import UUID

import pytest

from app.application.services.experiment_production_adapter import (
    ExperimentProductionAdapter,
)
from app.domain.decision import ProductionDecision
from app.domain.experimentation import ExperimentDimension, ExperimentVariant

ANGLE_ID = UUID("00000000-0000-0000-0000-000000000401")
DURATION_ID = UUID("00000000-0000-0000-0000-000000000402")
TOPIC_ID = UUID("00000000-0000-0000-0000-000000000403")


def test_topic_variant_produces_explicit_topic_override() -> None:
    variant = ExperimentVariant(TOPIC_ID, "B", ExperimentDimension.TOPIC, "Ancient Rome")
    result = ExperimentProductionAdapter().resolve(variant)

    assert result.topic == "Ancient Rome"
    assert result.angle is None


def test_angle_variant_cannot_bypass_m10_angle() -> None:
    variant = ExperimentVariant(ANGLE_ID, "B", ExperimentDimension.ANGLE, "contradiction")
    decision = ProductionDecision(angle="curiosity gap")

    with pytest.raises(ValueError, match="conflicts"):
        ExperimentProductionAdapter().resolve(variant, production_decision=decision)


def test_duration_variant_is_bounded_and_explicit() -> None:
    variant = ExperimentVariant(
        DURATION_ID,
        "B",
        ExperimentDimension.DURATION_TARGET_SECONDS,
        "35",
    )

    result = ExperimentProductionAdapter().resolve(variant)

    assert result.duration_target_seconds == Decimal("35")


def test_invalid_duration_is_rejected() -> None:
    variant = ExperimentVariant(
        DURATION_ID,
        "B",
        ExperimentDimension.DURATION_TARGET_SECONDS,
        "invalid",
    )

    with pytest.raises(ValueError, match="numeric"):
        ExperimentProductionAdapter().resolve(variant)
