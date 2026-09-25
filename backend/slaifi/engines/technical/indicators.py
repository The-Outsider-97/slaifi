"""Limited initial technical-analysis indicator set."""

from collections.abc import Sequence
from dataclasses import dataclass

from slaifi.domain.market import OHLCVBar
from slaifi.engines._validation import chronological_bars, positive_series
from slaifi.engines.features import rolling_mean
from slaifi.engines.utils.errors import EngineValidationError, InsufficientDataError

AlignedSeries = tuple[float | None, ...]


@dataclass(frozen=True, slots=True)
class MACDResult:
    macd_line: AlignedSeries
    signal_line: AlignedSeries
    histogram: AlignedSeries


def sma(values: Sequence[float], window: int) -> AlignedSeries:
    """Simple moving average with warm-up values set to None."""

    return rolling_mean(values, window)


def ema(values: Sequence[float], span: int) -> AlignedSeries:
    """EMA seeded with the SMA of the first span observations."""

    if span <= 0:
        raise EngineValidationError("span must be positive")
    data = positive_series(values, minimum=span, name="values")
    alpha = 2.0 / (span + 1.0)
    seed = sum(data[:span]) / span
    output: list[float | None] = [None] * (span - 1) + [seed]
    previous = seed
    for value in data[span:]:
        previous = alpha * value + (1.0 - alpha) * previous
        output.append(previous)
    return tuple(output)


def momentum(prices: Sequence[float], period: int) -> AlignedSeries:
    """Price momentum as a fractional return over period observations."""

    if period <= 0:
        raise EngineValidationError("period must be positive")
    data = positive_series(prices, minimum=period + 1, name="prices")
    output: list[float | None] = [None] * period
    output.extend(
        data[index] / data[index - period] - 1.0
        for index in range(period, len(data))
    )
    return tuple(output)


def rsi(prices: Sequence[float], period: int = 14) -> AlignedSeries:
    """Wilder RSI on close prices, returning 50 for a flat initial window."""

    if period <= 0:
        raise EngineValidationError("period must be positive")
    data = positive_series(prices, minimum=period + 1, name="prices")
    changes = [data[index] - data[index - 1] for index in range(1, len(data))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    output: list[float | None] = [None] * period
    output.append(_rsi_from_averages(avg_gain, avg_loss))

    for gain, loss in zip(gains[period:], losses[period:], strict=True):
        avg_gain = ((period - 1) * avg_gain + gain) / period
        avg_loss = ((period - 1) * avg_loss + loss) / period
        output.append(_rsi_from_averages(avg_gain, avg_loss))
    return tuple(output)


def _rsi_from_averages(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0.0:
        return 50.0 if avg_gain == 0.0 else 100.0
    relative_strength = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + relative_strength))


def macd(
    prices: Sequence[float],
    *,
    fast_span: int = 12,
    slow_span: int = 26,
    signal_span: int = 9,
) -> MACDResult:
    """MACD, signal, and histogram using SLAIFI's SMA-seeded EMA convention."""

    if not 0 < fast_span < slow_span:
        raise EngineValidationError("MACD requires 0 < fast_span < slow_span")
    if signal_span <= 0:
        raise EngineValidationError("signal_span must be positive")
    data = positive_series(
        prices,
        minimum=slow_span + signal_span - 1,
        name="prices",
    )
    fast = ema(data, fast_span)
    slow = ema(data, slow_span)

    macd_line: list[float | None] = []
    valid_macd: list[float] = []
    valid_indices: list[int] = []
    for index, (fast_value, slow_value) in enumerate(
        zip(fast, slow, strict=True)
    ):
        if fast_value is None or slow_value is None:
            macd_line.append(None)
            continue
        value = fast_value - slow_value
        macd_line.append(value)
        valid_macd.append(value)
        valid_indices.append(index)

    signal_valid = _ema_allow_signed(valid_macd, signal_span)
    signal_line: list[float | None] = [None] * len(data)
    for valid_index, signal_value in zip(
        valid_indices,
        signal_valid,
        strict=True,
    ):
        signal_line[valid_index] = signal_value

    histogram: list[float | None] = []
    for macd_value, signal_value in zip(
        macd_line,
        signal_line,
        strict=True,
    ):
        histogram.append(
            None
            if macd_value is None or signal_value is None
            else macd_value - signal_value
        )
    return MACDResult(tuple(macd_line), tuple(signal_line), tuple(histogram))


def _ema_allow_signed(values: Sequence[float], span: int) -> AlignedSeries:
    if len(values) < span:
        raise InsufficientDataError(f"EMA requires at least {span} observations")
    alpha = 2.0 / (span + 1.0)
    seed = sum(values[:span]) / span
    output: list[float | None] = [None] * (span - 1) + [seed]
    previous = seed
    for value in values[span:]:
        previous = alpha * value + (1.0 - alpha) * previous
        output.append(previous)
    return tuple(output)


def atr(bars: Sequence[OHLCVBar], period: int = 14) -> AlignedSeries:
    """Wilder Average True Range aligned to the source bars."""

    if period <= 0:
        raise EngineValidationError("period must be positive")
    data = chronological_bars(bars, minimum=period)
    true_ranges: list[float] = []
    previous_close: float | None = None
    for bar in data:
        high = float(bar.high)
        low = float(bar.low)
        close = float(bar.close)
        if previous_close is None:
            true_range = high - low
        else:
            true_range = max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )
        true_ranges.append(true_range)
        previous_close = close

    seed = sum(true_ranges[:period]) / period
    output: list[float | None] = [None] * (period - 1) + [seed]
    previous_atr = seed
    for true_range in true_ranges[period:]:
        previous_atr = ((period - 1) * previous_atr + true_range) / period
        output.append(previous_atr)
    return tuple(output)
