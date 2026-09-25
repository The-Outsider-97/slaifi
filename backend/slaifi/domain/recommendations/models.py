"""Recommendation vocabulary only; no recommendation-generation logic."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from math import isfinite

from slaifi.domain.assets import AssetId
from slaifi.domain.predictions import ConfidenceMeasure, UncertaintyMeasure
from slaifi.domain.utils.errors import DomainValidationError


class RecommendationAction(StrEnum):
    BUY = "BUY"
    STRONG_BUY = "STRONG_BUY"
    HOLD = "HOLD"
    DCA = "DCA"
    REDUCE = "REDUCE"
    PARTIAL_SELL = "PARTIAL_SELL"
    SELL = "SELL"
    SHORT = "SHORT"
    COVER = "COVER"
    AVOID = "AVOID"
    WATCH = "WATCH"


class RiskLevel(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"


@dataclass(frozen=True, slots=True)
class ModelVersion:
    name: str
    version: str

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.version.strip():
            raise DomainValidationError("model name and version must not be empty")


@dataclass(frozen=True, slots=True)
class Recommendation:
    """Future recommendation record that preserves evidence references."""

    action: RecommendationAction
    asset: AssetId
    generated_at: datetime
    time_horizon: timedelta
    target_context: str
    risk_level: RiskLevel
    confidence: ConfidenceMeasure | None = None
    uncertainty: UncertaintyMeasure | None = None
    expected_return_rate: float | None = None
    expected_downside_rate: float | None = None
    reasoning_references: tuple[str, ...] = ()
    supporting_signals: tuple[str, ...] = ()
    conflicting_signals: tuple[str, ...] = ()
    invalidation_conditions: tuple[str, ...] = ()
    model_versions: tuple[ModelVersion, ...] = ()

    def __post_init__(self) -> None:
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise DomainValidationError("generated_at must be timezone-aware")
        if self.time_horizon <= timedelta(0):
            raise DomainValidationError("time_horizon must be positive")
        if not self.target_context.strip():
            raise DomainValidationError("target_context must not be empty")
        if self.expected_return_rate is not None and not isfinite(self.expected_return_rate):
            raise DomainValidationError("expected_return_rate must be finite")
        if self.expected_downside_rate is not None and (
            not isfinite(self.expected_downside_rate) or self.expected_downside_rate < 0.0
        ):
            raise DomainValidationError(
                "expected_downside_rate is a non-negative downside magnitude"
            )
