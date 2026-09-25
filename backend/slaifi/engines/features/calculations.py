"""Reference quantitative feature calculations with explicit alignment."""

import math
import statistics
from collections.abc import Sequence

from slaifi.core.exceptions import ValidationError
from slaifi.engines._validation import finite_series, positive_series

AlignedSeries = tuple[float | None, ...]


def simple_returns(prices: Sequence[float]) -> AlignedSeries:
    values = positive_series(prices, minimum=2, name="prices")
    return (None, *(values[i] / values[i - 1] - 1.0 for i in range(1, len(values))))


def log_returns(prices: Sequence[float]) -> AlignedSeries:
    values = positive_series(prices, minimum=2, name="prices")
    return (None, *(math.log(values[i] / values[i - 1]) for i in range(1, len(values))))


def rolling_returns(prices: Sequence[float], window: int) -> AlignedSeries:
    if window <= 0: raise ValidationError("window must be positive")
    values = positive_series(prices, minimum=window + 1, name="prices")
    return (*([None] * window), *(values[i] / values[i - window] - 1.0 for i in range(window, len(values))))


def rolling_mean(values: Sequence[float], window: int) -> AlignedSeries:
    if window <= 0: raise ValidationError("window must be positive")
    data = finite_series(values, minimum=window, name="values")
    result: list[float | None] = [None] * (window - 1)
    running = sum(data[:window]); result.append(running / window)
    for i in range(window, len(data)):
        running += data[i] - data[i-window]; result.append(running/window)
    return tuple(result)


def rolling_max(values: Sequence[float], window: int) -> AlignedSeries:
    if window <= 0: raise ValidationError("window must be positive")
    data = finite_series(values, minimum=window, name="values")
    return (*([None] * (window - 1)), *(max(data[i-window+1:i+1]) for i in range(window-1, len(data))))


def rolling_volatility(prices: Sequence[float], window: int, *, periods_per_year: int | None = None) -> AlignedSeries:
    if window < 2: raise ValidationError("rolling volatility window must be at least 2")
    if periods_per_year is not None and periods_per_year <= 0: raise ValidationError("periods_per_year must be positive")
    values = positive_series(prices, minimum=window + 1, name="prices")
    returns = [values[i]/values[i-1]-1.0 for i in range(1,len(values))]
    scale = math.sqrt(periods_per_year) if periods_per_year is not None else 1.0
    result: list[float | None] = [None] * window
    for ending in range(window, len(values)):
        result.append(statistics.stdev(returns[ending-window:ending]) * scale)
    return tuple(result)


def drawdown_series(values: Sequence[float]) -> tuple[float, ...]:
    data = positive_series(values, minimum=1, name="values")
    peak = data[0]; output=[]
    for value in data:
        peak=max(peak,value); output.append(value/peak-1.0)
    return tuple(output)


def volume_changes(volumes: Sequence[float]) -> AlignedSeries:
    data = finite_series(volumes, minimum=2, name="volumes")
    if any(value < 0 for value in data): raise ValidationError("volumes cannot be negative")
    output: list[float | None] = [None]
    for previous,current in zip(data,data[1:]): output.append(None if previous==0 else current/previous-1.0)
    return tuple(output)
