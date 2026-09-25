"""Calculated risk result types."""

from dataclasses import dataclass
from math import isfinite

from slaifi.domain.utils.errors import DomainValidationError


@dataclass(frozen=True, slots=True)
class RiskStatistics:
    """Initial portfolio/security risk statistics with explicit annualization."""

    observation_count: int
    periods_per_year: int
    annualized_volatility: float
    annualized_downside_deviation: float
    maximum_drawdown: float
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    concentration_hhi: float | None = None

    def __post_init__(self) -> None:
        if self.observation_count < 1:
            raise DomainValidationError("observation_count must be positive")
        if self.periods_per_year <= 0:
            raise DomainValidationError("periods_per_year must be positive")
        finite_values = (
            self.annualized_volatility,
            self.annualized_downside_deviation,
            self.maximum_drawdown,
        )
        if not all(isfinite(value) for value in finite_values):
            raise DomainValidationError("risk statistics must be finite")
        if self.annualized_volatility < 0 or self.annualized_downside_deviation < 0:
            raise DomainValidationError("volatility measures cannot be negative")
        if not -1.0 <= self.maximum_drawdown <= 0.0:
            raise DomainValidationError("maximum_drawdown must be in [-1, 0]")
        for name, value in (
            ("sharpe_ratio", self.sharpe_ratio),
            ("sortino_ratio", self.sortino_ratio),
            ("concentration_hhi", self.concentration_hhi),
        ):
            if value is not None and not isfinite(value):
                raise DomainValidationError(f"{name} must be finite when supplied")
        if self.concentration_hhi is not None and not 0.0 < self.concentration_hhi <= 1.0:
            raise DomainValidationError("concentration_hhi must be in (0, 1]")


@dataclass(frozen=True, slots=True)
class CorrelationMatrix:
    """Symmetric matrix of defined Pearson correlations."""

    labels: tuple[str, ...]
    values: tuple[tuple[float, ...], ...]

    def __post_init__(self) -> None:
        size = len(self.labels)
        if size == 0 or len(self.values) != size:
            raise DomainValidationError("correlation matrix must be non-empty and square")
        if len(set(self.labels)) != size:
            raise DomainValidationError("correlation labels must be unique")
        for row_index, row in enumerate(self.values):
            if len(row) != size:
                raise DomainValidationError("correlation matrix must be square")
            for column_index, value in enumerate(row):
                if not isfinite(value) or not -1.0 <= value <= 1.0:
                    raise DomainValidationError("correlations must be finite and in [-1, 1]")
                if row_index == column_index and abs(value - 1.0) > 1e-12:
                    raise DomainValidationError("correlation matrix diagonal must equal 1")
                if abs(value - self.values[column_index][row_index]) > 1e-12:
                    raise DomainValidationError("correlation matrix must be symmetric")
