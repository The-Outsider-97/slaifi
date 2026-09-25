import math
import statistics

import pytest

from slaifi.core.exceptions import FinancialCalculationError, ValidationError
from slaifi.engines.risk import (
    calculate_risk_statistics,
    concentration_hhi,
    correlation_matrix,
    downside_deviation,
    historical_volatility,
    maximum_drawdown,
    pearson_correlation,
    sharpe_ratio,
    sortino_ratio,
)

RETURNS = [0.10, -0.05, 0.02, -0.01]


def test_historical_volatility_reference() -> None:
    expected = statistics.stdev(RETURNS) * math.sqrt(12)
    assert historical_volatility(
        RETURNS,
        periods_per_year=12,
    ) == pytest.approx(expected)


def test_downside_deviation_reference() -> None:
    expected = math.sqrt(
        (0.0**2 + (-0.05) ** 2 + 0.0**2 + (-0.01) ** 2) / 4
    ) * math.sqrt(12)
    assert downside_deviation(
        RETURNS,
        periods_per_year=12,
    ) == pytest.approx(expected)


def test_maximum_drawdown_reference() -> None:
    assert maximum_drawdown([100.0, 120.0, 90.0, 96.0]) == pytest.approx(-0.25)


def test_sharpe_reference_zero_risk_free() -> None:
    expected = (
        statistics.mean(RETURNS)
        / statistics.stdev(RETURNS)
        * math.sqrt(12)
    )
    assert sharpe_ratio(
        RETURNS,
        periods_per_year=12,
    ) == pytest.approx(expected)


def test_sortino_reference_zero_target() -> None:
    downside = downside_deviation(RETURNS, periods_per_year=12)
    expected = statistics.mean(RETURNS) * 12 / downside
    assert sortino_ratio(
        RETURNS,
        periods_per_year=12,
    ) == pytest.approx(expected)


def test_correlation_reference_and_matrix() -> None:
    assert pearson_correlation(
        [1, 2, 3],
        [2, 4, 6],
    ) == pytest.approx(1.0)
    matrix = correlation_matrix({"A": [1, 2, 3], "B": [3, 2, 1]})
    assert matrix.values[0][1] == pytest.approx(-1.0)
    assert matrix.values[1][0] == pytest.approx(-1.0)


def test_correlation_rejects_constant_series() -> None:
    with pytest.raises(FinancialCalculationError, match="constant"):
        pearson_correlation([1, 1, 1], [1, 2, 3])


def test_concentration_hhi_reference() -> None:
    assert concentration_hhi([0.5, 0.5]) == pytest.approx(0.5)
    assert concentration_hhi([1.0, 0.0]) == pytest.approx(1.0)


def test_risk_statistics_marks_undefined_ratios_as_none() -> None:
    report = calculate_risk_statistics(
        [0.01, 0.01, 0.01],
        [100.0, 101.0, 102.0],
        periods_per_year=12,
        weights=[0.5, 0.5],
    )
    assert report.sharpe_ratio is None
    assert report.sortino_ratio is None
    assert report.concentration_hhi == pytest.approx(0.5)


def test_risk_engine_rejects_invalid_annualization() -> None:
    with pytest.raises(ValidationError, match="periods_per_year"):
        historical_volatility([0.1, 0.2], periods_per_year=0)
