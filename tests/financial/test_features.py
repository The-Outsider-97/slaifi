import math
import statistics

import pytest

from slaifi.core.exceptions import InsufficientDataError, ValidationError
from slaifi.engines.features import (
    drawdown_series,
    log_returns,
    rolling_max,
    rolling_mean,
    rolling_returns,
    rolling_volatility,
    simple_returns,
    volume_changes,
)


def test_simple_returns_reference_values() -> None:
    result = simple_returns([100.0, 110.0, 99.0])
    assert result[0] is None
    assert result[1] == pytest.approx(0.10)
    assert result[2] == pytest.approx(-0.10)


def test_log_returns_reference_values() -> None:
    result = log_returns([100.0, 110.0])
    assert result == (None, pytest.approx(math.log(1.1)))


def test_rolling_return_alignment() -> None:
    result = rolling_returns([100.0, 110.0, 121.0], 2)
    assert result == (None, None, pytest.approx(0.21))


def test_rolling_mean_reference() -> None:
    assert rolling_mean([1.0, 2.0, 3.0, 4.0], 3) == (
        None,
        None,
        2.0,
        3.0,
    )


def test_rolling_max_reference() -> None:
    assert rolling_max([1.0, 3.0, 2.0, 5.0], 2) == (
        None,
        3.0,
        3.0,
        5.0,
    )


def test_rolling_volatility_explicit_annualization() -> None:
    prices = [100.0, 110.0, 99.0, 108.9]
    result = rolling_volatility(prices, 3, periods_per_year=4)
    expected = statistics.stdev([0.10, -0.10, 0.10]) * math.sqrt(4)
    assert result[-1] == pytest.approx(expected)


def test_drawdown_reference() -> None:
    assert drawdown_series([100.0, 120.0, 90.0, 96.0]) == pytest.approx(
        (0.0, 0.0, -0.25, -0.20)
    )


def test_volume_zero_denominator_is_undefined() -> None:
    assert volume_changes([0.0, 10.0, 20.0]) == (None, None, 1.0)


def test_features_reject_nonfinite_and_insufficient_inputs() -> None:
    with pytest.raises(ValidationError):
        simple_returns([100.0, float("nan")])
    with pytest.raises(ValidationError):
        simple_returns([100.0, 0.0])
    with pytest.raises(InsufficientDataError):
        rolling_returns([100.0, 101.0], 2)
