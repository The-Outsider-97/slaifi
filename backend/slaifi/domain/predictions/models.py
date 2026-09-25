"""Prediction contracts without model implementations."""
from dataclasses import dataclass
from datetime import datetime,timedelta
from decimal import Decimal
from math import isfinite
from slaifi.core.exceptions import ValidationError
from slaifi.domain.assets import AssetId

def _aware(value: datetime,name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None: raise ValidationError(f"{name} must be timezone-aware")

@dataclass(frozen=True, slots=True)
class PredictionInterval:
    lower_return_rate: float
    upper_return_rate: float
    coverage_probability: float | None = None
    def __post_init__(self) -> None:
        if not isfinite(self.lower_return_rate) or not isfinite(self.upper_return_rate): raise ValidationError("prediction interval bounds must be finite")
        if self.lower_return_rate>self.upper_return_rate: raise ValidationError("prediction interval lower bound cannot exceed upper bound")
        if self.coverage_probability is not None and not (isfinite(self.coverage_probability) and 0<self.coverage_probability<1): raise ValidationError("coverage_probability must be in (0, 1)")

@dataclass(frozen=True, slots=True)
class ConfidenceMeasure:
    method: str
    value: float
    def __post_init__(self) -> None:
        if not self.method.strip() or not isfinite(self.value) or not 0<=self.value<=1: raise ValidationError("confidence must have a method and value in [0, 1]")

@dataclass(frozen=True, slots=True)
class UncertaintyMeasure:
    method: str
    value: float
    unit: str
    def __post_init__(self) -> None:
        if not self.method.strip() or not self.unit.strip() or not isfinite(self.value) or self.value<0: raise ValidationError("uncertainty requires method, unit, and non-negative finite value")

@dataclass(frozen=True, slots=True)
class Prediction:
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
        if self.horizon<=timedelta(0): raise ValidationError("prediction horizon must be positive")
        _aware(self.generated_at,"generated_at"); _aware(self.input_data_at,"input_data_at")
        if self.input_data_at>self.generated_at: raise ValidationError("input_data_at cannot be later than generated_at")
        if not self.model_name.strip() or not self.model_version.strip(): raise ValidationError("model name and version must not be empty")
        if self.expected_return_rate is None and self.expected_price is None: raise ValidationError("prediction requires an expected return or expected price")
        if self.expected_return_rate is not None and not isfinite(self.expected_return_rate): raise ValidationError("expected_return_rate must be finite")
        if self.expected_price is not None and self.expected_price<=0: raise ValidationError("expected_price must be positive")
