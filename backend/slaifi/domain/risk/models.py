"""Calculated risk result types."""
from dataclasses import dataclass
from math import isfinite
from slaifi.core.exceptions import ValidationError

@dataclass(frozen=True, slots=True)
class RiskStatistics:
    observation_count: int
    periods_per_year: int
    annualized_volatility: float
    annualized_downside_deviation: float
    maximum_drawdown: float
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    concentration_hhi: float | None = None
    def __post_init__(self) -> None:
        if self.observation_count < 1: raise ValidationError("observation_count must be positive")
        if self.periods_per_year <= 0: raise ValidationError("periods_per_year must be positive")
        if not all(isfinite(v) for v in (self.annualized_volatility,self.annualized_downside_deviation,self.maximum_drawdown)): raise ValidationError("risk statistics must be finite")
        if self.annualized_volatility < 0 or self.annualized_downside_deviation < 0: raise ValidationError("volatility measures cannot be negative")
        if not -1 <= self.maximum_drawdown <= 0: raise ValidationError("maximum_drawdown must be in [-1, 0]")
        if self.concentration_hhi is not None and not 0 < self.concentration_hhi <= 1: raise ValidationError("concentration_hhi must be in (0, 1]")

@dataclass(frozen=True, slots=True)
class CorrelationMatrix:
    labels: tuple[str, ...]
    values: tuple[tuple[float, ...], ...]
    def __post_init__(self) -> None:
        n=len(self.labels)
        if n==0 or len(self.values)!=n: raise ValidationError("correlation matrix must be non-empty and square")
        if len(set(self.labels))!=n: raise ValidationError("correlation labels must be unique")
        for i,row in enumerate(self.values):
            if len(row)!=n: raise ValidationError("correlation matrix must be square")
            for j,value in enumerate(row):
                if not isfinite(value) or not -1<=value<=1: raise ValidationError("correlations must be finite and in [-1, 1]")
                if i==j and abs(value-1)>1e-12: raise ValidationError("correlation matrix diagonal must equal 1")
                if abs(value-self.values[j][i])>1e-12: raise ValidationError("correlation matrix must be symmetric")
