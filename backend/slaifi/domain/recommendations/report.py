"""Auditable recommendation report produced by the deterministic recommendation engine.

The report separates observations (signals), rule-based scores, strategy constraint findings,
validated predictions and explicit insufficient-evidence outcomes. ``signal_score`` is a
rule-based aggregate in [-1, 1]; it is **not** a probability and no confidence is invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from slaifi.domain.assets import AssetId
from slaifi.domain.predictions import Prediction
from slaifi.domain.recommendations.models import ModelVersion, RecommendationAction, RiskLevel
from slaifi.domain.utils import DomainValidationError, require_aware_datetime


class ReportStatus(StrEnum):
    RECOMMENDATION = "recommendation"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class SignalDirection(StrEnum):
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class SignalReading:
    """One observed indicator and the rule that turned it into a directional vote."""

    name: str
    value: float | None
    direction: SignalDirection
    weight: float
    vote: float  # signed contribution in [-weight, +weight]
    rationale: str


@dataclass(frozen=True, slots=True)
class ConstraintFinding:
    """Strategy compatibility finding. Hard findings always override preferences."""

    code: str
    severity: str  # hard | soft
    message: str
    limit: float | None = None
    observed: float | None = None

    def __post_init__(self) -> None:
        if self.severity not in {"hard", "soft"}:
            raise DomainValidationError("constraint severity must be 'hard' or 'soft'")


@dataclass(frozen=True, slots=True)
class PredictionValidation:
    """Out-of-sample calibration of the interval model on this asset's own history."""

    method: str
    nominal_coverage: float
    realized_coverage: float | None
    test_count: int
    mean_interval_width: float | None
    passed: bool
    note: str


@dataclass(frozen=True, slots=True)
class RecommendationReport:
    asset: AssetId
    generated_at: datetime
    horizon_days: int
    strategy_id: str
    status: ReportStatus
    action: RecommendationAction | None
    signal_score: float | None
    risk_level: RiskLevel | None
    signals: tuple[SignalReading, ...] = ()
    supporting_signals: tuple[str, ...] = ()
    conflicting_signals: tuple[str, ...] = ()
    invalidation_conditions: tuple[str, ...] = ()
    constraint_findings: tuple[ConstraintFinding, ...] = ()
    insufficient_reasons: tuple[str, ...] = ()
    prediction: Prediction | None = None
    prediction_validation: PredictionValidation | None = None
    expected_downside_rate: float | None = None
    observation_count: int = 0
    last_bar_at: datetime | None = None
    data_mode: str = "unknown"
    illustrative: bool = False
    position_quantity: str | None = None
    model_versions: tuple[ModelVersion, ...] = ()
    summary: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        require_aware_datetime(self.generated_at, name="generated_at")
        if self.status is ReportStatus.RECOMMENDATION and self.action is None:
            raise DomainValidationError("a recommendation report requires an action")
        if self.status is ReportStatus.INSUFFICIENT_EVIDENCE:
            if self.action is not None:
                raise DomainValidationError("insufficient evidence cannot carry an action")
            if not self.insufficient_reasons:
                raise DomainValidationError("insufficient evidence must explain why")
