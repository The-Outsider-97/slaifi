"""Prediction contracts without model implementations."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from math import isfinite

from slaifi.domain.assets import AssetId
from slaifi.domain.utils.errors import DomainValidationError


def _aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainValidationError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class PredictionInterval:
    lower_return_rate: float
    upper_return_rate: float
    coverage_probability: float | None = None

    def __post_init__(self) -> None:
        if not isfinite(self.lower_return_rate) or not isfinite(self.upper_return_rate):
            raise DomainValidationError("prediction interval bounds must be finite")
        if self.lower_return_rate > self.upper_return_rate:
            raise DomainValidationError("prediction interval lower bound cannot exceed upper bound")
        if self.coverage_probability is not None and not (
            isfinite(self.coverage_probability)
            and 0.0 < self.coverage_probability < 1.0
        ):
            raise DomainValidationError("coverage_probability must be in (0, 1)")


@dataclass(frozen=True, slots=True)
class ConfidenceMeasure:
    """Named confidence measure; not interchangeable with uncertainty."""

    method: str
    value: float

    def __post_init__(self) -> None:
        if not self.method.strip():
            raise DomainValidationError("confidence method must not be empty")
        if not isfinite(self.value) or not 0.0 <= self.value <= 1.0:
            raise DomainValidationError("confidence value must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class UncertaintyMeasure:
    """Named uncertainty measure with an explicit unit or scale."""

    method: str
    value: float
    unit: str

    def __post_init__(self) -> None:
        if not self.method.strip() or not self.unit.strip():
            raise DomainValidationError("uncertainty method and unit must not be empty")
        if not isfinite(self.value) or self.value < 0.0:
            raise DomainValidationError("uncertainty value must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class Prediction:
    """Auditable future prediction record independent of model family."""

    asset: AssetId
    horizon: timedelta
    generated_at: datetime
    input_data_at: datetime
    model_name: str
    model_version: str
    expected_return_rate: float | None = None
    expected_price: Decimal | None = None
    interval: PredictionInterval | None = None
    confidence: ConfidenceMeasure | None = None
    uncertainty: UncertaintyMeasure | None = None

    def __post_init__(self) -> None:
        if self.horizon <= timedelta(0):
            raise DomainValidationError("prediction horizon must be positive")
        _aware(self.generated_at, "generated_at")
        _aware(self.input_data_at, "input_data_at")
        if self.input_data_at > self.generated_at:
            raise DomainValidationError("input_data_at cannot be later than generated_at")
        if not self.model_name.strip() or not self.model_version.strip():
            raise DomainValidationError("model name and version must not be empty")
        if self.expected_return_rate is None and self.expected_price is None:
            raise DomainValidationError("prediction requires an expected return or expected price")
        if self.expected_return_rate is not None and not isfinite(self.expected_return_rate):
            raise DomainValidationError("expected_return_rate must be finite")
        if self.expected_price is not None and self.expected_price <= 0:
            raise DomainValidationError("expected_price must be positive")
