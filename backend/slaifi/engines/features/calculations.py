"""Reference quantitative feature calculations with explicit alignment."""

import math
import statistics
from collections.abc import Sequence

from slaifi.engines._validation import finite_series, positive_series
from slaifi.engines.utils.errors import EngineValidationError

AlignedSeries = tuple[float | None, ...]


def simple_returns(prices: Sequence[float]) -> AlignedSeries:
    """Return period-over-period simple returns aligned to input prices."""

    values = positive_series(prices, minimum=2, name="prices")
    result: list[float | None] = [None]
    result.extend(
        values[index] / values[index - 1] - 1.0
        for index in range(1, len(values))
    )
    return tuple(result)


def log_returns(prices: Sequence[float]) -> AlignedSeries:
    """Return natural-log returns aligned to input prices."""

    values = positive_series(prices, minimum=2, name="prices")
    result: list[float | None] = [None]
    result.extend(
        math.log(values[index] / values[index - 1])
        for index in range(1, len(values))
    )
    return tuple(result)


def rolling_returns(prices: Sequence[float], window: int) -> AlignedSeries:
    """Return price[t] / price[t-window] - 1 with warm-up None values."""

    if window <= 0:
        raise EngineValidationError("window must be positive")
    values = positive_series(prices, minimum=window + 1, name="prices")
    result: list[float | None] = [None] * window
    result.extend(
        values[index] / values[index - window] - 1.0
        for index in range(window, len(values))
    )
    return tuple(result)


def rolling_mean(values: Sequence[float], window: int) -> AlignedSeries:
    """Simple rolling arithmetic mean with right-edge alignment."""

    if window <= 0:
        raise EngineValidationError("window must be positive")
    data = finite_series(values, minimum=window, name="values")
    result: list[float | None] = [None] * (window - 1)
    running = sum(data[:window])
    result.append(running / window)
    for index in range(window, len(data)):
        running += data[index] - data[index - window]
        result.append(running / window)
    return tuple(result)


def rolling_max(values: Sequence[float], window: int) -> AlignedSeries:
    """Rolling maximum with explicit warm-up values."""

    if window <= 0:
        raise EngineValidationError("window must be positive")
    data = finite_series(values, minimum=window, name="values")
    result: list[float | None] = [None] * (window - 1)
    result.extend(
        max(data[index - window + 1 : index + 1])
        for index in range(window - 1, len(data))
    )
    return tuple(result)


def rolling_volatility(
    prices: Sequence[float],
    window: int,
    *,
    periods_per_year: int | None = None,
) -> AlignedSeries:
    """Sample volatility over a rolling return window."""

    if window < 2:
        raise EngineValidationError("rolling volatility window must be at least 2")
    if periods_per_year is not None and periods_per_year <= 0:
        raise EngineValidationError("periods_per_year must be positive")
    prices_tuple = positive_series(
        prices,
        minimum=window + 1,
        name="prices",
    )
    raw_returns = [
        prices_tuple[index] / prices_tuple[index - 1] - 1.0
        for index in range(1, len(prices_tuple))
    ]
    scale = math.sqrt(periods_per_year) if periods_per_year is not None else 1.0
    result: list[float | None] = [None] * window
    for ending in range(window, len(prices_tuple)):
        sample = raw_returns[ending - window : ending]
        result.append(statistics.stdev(sample) * scale)
    return tuple(result)


def drawdown_series(values: Sequence[float]) -> tuple[float, ...]:
    """Return drawdown from the running peak as negative fractional rates."""

    data = positive_series(values, minimum=1, name="values")
    peak = data[0]
    output: list[float] = []
    for value in data:
        peak = max(peak, value)
        output.append(value / peak - 1.0)
    return tuple(output)


def volume_changes(volumes: Sequence[float]) -> AlignedSeries:
    """Period-over-period volume change; zero prior volume yields None."""

    data = finite_series(volumes, minimum=2, name="volumes")
    if any(value < 0.0 for value in data):
        raise EngineValidationError("volumes cannot be negative")
    output: list[float | None] = [None]
    for previous, current in zip(data, data[1:], strict=False):
        output.append(None if previous == 0.0 else current / previous - 1.0)
    return tuple(output)
