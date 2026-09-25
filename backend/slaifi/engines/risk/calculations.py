"""Reference statistical risk calculations with explicit annualization inputs."""

import math
import statistics
from collections.abc import Mapping, Sequence

from slaifi.domain.risk import CorrelationMatrix, RiskStatistics
from slaifi.engines._validation import finite_series, positive_series
from slaifi.engines.utils.errors import EngineValidationError, FinancialCalculationError


def periodic_rate_from_annual(
    annual_rate: float,
    periods_per_year: int,
) -> float:
    """Convert an annual compound rate to an equivalent periodic rate."""

    if periods_per_year <= 0:
        raise EngineValidationError("periods_per_year must be positive")
    if not math.isfinite(annual_rate) or annual_rate <= -1.0:
        raise EngineValidationError("annual_rate must be finite and greater than -1")
    return (1.0 + annual_rate) ** (1.0 / periods_per_year) - 1.0


def historical_volatility(
    returns: Sequence[float],
    *,
    periods_per_year: int,
) -> float:
    """Annualized sample standard deviation of periodic simple returns."""

    data = finite_series(returns, minimum=2, name="returns")
    if periods_per_year <= 0:
        raise EngineValidationError("periods_per_year must be positive")
    return statistics.stdev(data) * math.sqrt(periods_per_year)


def downside_deviation(
    returns: Sequence[float],
    *,
    periods_per_year: int,
    target_annual_rate: float = 0.0,
) -> float:
    """Annualized target downside deviation over all observations."""

    data = finite_series(returns, minimum=1, name="returns")
    target_periodic = periodic_rate_from_annual(
        target_annual_rate,
        periods_per_year,
    )
    mean_squared_downside = sum(
        min(value - target_periodic, 0.0) ** 2 for value in data
    ) / len(data)
    return math.sqrt(mean_squared_downside) * math.sqrt(periods_per_year)


def maximum_drawdown(values: Sequence[float]) -> float:
    """Worst peak-to-trough drawdown as a negative fractional rate."""

    data = positive_series(values, minimum=1, name="equity values")
    peak = data[0]
    worst = 0.0
    for value in data:
        peak = max(peak, value)
        worst = min(worst, value / peak - 1.0)
    return worst


def sharpe_ratio(
    returns: Sequence[float],
    *,
    periods_per_year: int,
    risk_free_annual_rate: float = 0.0,
) -> float:
    """Annualized arithmetic Sharpe ratio."""

    data = finite_series(returns, minimum=2, name="returns")
    risk_free_periodic = periodic_rate_from_annual(
        risk_free_annual_rate,
        periods_per_year,
    )
    volatility = statistics.stdev(data)
    if volatility == 0.0:
        raise FinancialCalculationError(
            "Sharpe ratio is undefined for zero volatility"
        )
    mean_excess = statistics.mean(
        value - risk_free_periodic for value in data
    )
    return mean_excess / volatility * math.sqrt(periods_per_year)


def sortino_ratio(
    returns: Sequence[float],
    *,
    periods_per_year: int,
    target_annual_rate: float = 0.0,
) -> float:
    """Annualized Sortino ratio using target downside deviation."""

    data = finite_series(returns, minimum=1, name="returns")
    target_periodic = periodic_rate_from_annual(
        target_annual_rate,
        periods_per_year,
    )
    downside = downside_deviation(
        data,
        periods_per_year=periods_per_year,
        target_annual_rate=target_annual_rate,
    )
    if downside == 0.0:
        raise FinancialCalculationError(
            "Sortino ratio is undefined with zero downside deviation"
        )
    annualized_excess = (
        statistics.mean(value - target_periodic for value in data)
        * periods_per_year
    )
    return annualized_excess / downside


def pearson_correlation(
    left: Sequence[float],
    right: Sequence[float],
) -> float:
    """Sample Pearson correlation for equal-length finite series."""

    if len(left) != len(right):
        raise EngineValidationError("correlation series must have equal length")
    x = finite_series(left, minimum=2, name="left correlation series")
    y = finite_series(right, minimum=2, name="right correlation series")
    mean_x = statistics.mean(x)
    mean_y = statistics.mean(y)
    numerator = sum(
        (a - mean_x) * (b - mean_y)
        for a, b in zip(x, y, strict=True)
    )
    sum_sq_x = sum((a - mean_x) ** 2 for a in x)
    sum_sq_y = sum((b - mean_y) ** 2 for b in y)
    denominator = math.sqrt(sum_sq_x * sum_sq_y)
    if denominator == 0.0:
        raise FinancialCalculationError(
            "correlation is undefined for a constant series"
        )
    value = numerator / denominator
    return max(-1.0, min(1.0, value))


def correlation_matrix(
    series: Mapping[str, Sequence[float]],
) -> CorrelationMatrix:
    """Calculate a symmetric Pearson correlation matrix."""

    labels = tuple(series.keys())
    if not labels:
        raise EngineValidationError("correlation matrix requires at least one series")
    lengths = {len(series[label]) for label in labels}
    if len(lengths) != 1:
        raise EngineValidationError("all correlation series must have equal length")
    validated = {
        label: finite_series(series[label], minimum=2, name=label)
        for label in labels
    }
    for label, values in validated.items():
        if statistics.pstdev(values) == 0.0:
            raise FinancialCalculationError(
                f"correlation is undefined for constant series {label}"
            )

    rows: list[tuple[float, ...]] = []
    for left in labels:
        row: list[float] = []
        for right in labels:
            row.append(
                1.0
                if left == right
                else pearson_correlation(
                    validated[left],
                    validated[right],
                )
            )
        rows.append(tuple(row))
    return CorrelationMatrix(labels=labels, values=tuple(rows))


def concentration_hhi(weights: Sequence[float]) -> float:
    """Herfindahl-Hirschman concentration after non-negative normalization."""

    data = finite_series(weights, minimum=1, name="weights")
    if any(weight < 0.0 for weight in data):
        raise EngineValidationError("concentration weights cannot be negative")
    total = sum(data)
    if total <= 0.0:
        raise FinancialCalculationError(
            "concentration is undefined when total weight is zero"
        )
    normalized = [weight / total for weight in data]
    return sum(weight * weight for weight in normalized)


def calculate_risk_statistics(
    returns: Sequence[float],
    equity_values: Sequence[float],
    *,
    periods_per_year: int,
    risk_free_annual_rate: float = 0.0,
    target_annual_rate: float = 0.0,
    weights: Sequence[float] | None = None,
) -> RiskStatistics:
    """Assemble the initial SLAIFI risk report from normalized inputs."""

    data = finite_series(returns, minimum=2, name="returns")
    volatility = historical_volatility(
        data,
        periods_per_year=periods_per_year,
    )
    downside = downside_deviation(
        data,
        periods_per_year=periods_per_year,
        target_annual_rate=target_annual_rate,
    )
    sharpe: float | None
    try:
        sharpe = sharpe_ratio(
            data,
            periods_per_year=periods_per_year,
            risk_free_annual_rate=risk_free_annual_rate,
        )
    except FinancialCalculationError:
        sharpe = None
    sortino: float | None
    try:
        sortino = sortino_ratio(
            data,
            periods_per_year=periods_per_year,
            target_annual_rate=target_annual_rate,
        )
    except FinancialCalculationError:
        sortino = None

    return RiskStatistics(
        observation_count=len(data),
        periods_per_year=periods_per_year,
        annualized_volatility=volatility,
        annualized_downside_deviation=downside,
        maximum_drawdown=maximum_drawdown(equity_values),
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        concentration_hhi=(
            concentration_hhi(weights) if weights is not None else None
        ),
    )
