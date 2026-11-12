"""Causal indicator frame and rule-based directional readings.

Every value at index ``t`` is computed from closes ``<= t`` only (the underlying indicators are
trailing), so the same frame can drive both the live recommendation and a look-ahead-free
backtest. A reading's *vote* is a bounded, rule-based directional score; it is not a probability.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from slaifi.domain.recommendations import SignalDirection, SignalReading
from slaifi.engines.technical import macd, momentum, rsi, sma
from slaifi.engines.utils.errors import InsufficientDataError

FAST_WINDOW = 20
SLOW_WINDOW = 50
LONG_WINDOW = 200
MOMENTUM_WINDOW = 63
RSI_PERIOD = 14
MACD_MIN_BARS = 35  # slow 26 + signal 9 - 1
MIN_BARS_FOR_SIGNALS = SLOW_WINDOW + 10

# Rule weights (documented in docs/finance/recommendation-methodology.md).
WEIGHT_TREND_SLOW = 0.25
WEIGHT_TREND_LONG = 0.15
WEIGHT_MOMENTUM = 0.20
WEIGHT_MACD = 0.15
WEIGHT_RSI = 0.10
WEIGHT_CROSS = 0.15

MOMENTUM_FULL_SCALE = 0.15  # a 15% 63-bar move saturates the momentum vote
TREND_FULL_SCALE = 0.05  # price 5% above/below its average saturates the trend vote
RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0


@dataclass(frozen=True, slots=True)
class IndicatorFrame:
    closes: tuple[float, ...]
    sma_fast: tuple[float | None, ...]
    sma_slow: tuple[float | None, ...]
    sma_long: tuple[float | None, ...]
    momentum: tuple[float | None, ...]
    rsi: tuple[float | None, ...]
    macd_hist: tuple[float | None, ...]
    macd_line: tuple[float | None, ...]
    macd_signal: tuple[float | None, ...]

    def __len__(self) -> int:
        return len(self.closes)


def _none_series(length: int) -> tuple[float | None, ...]:
    return (None,) * length


def _safe(fn, closes: Sequence[float], *args, **kwargs) -> tuple[float | None, ...]:  # type: ignore[no-untyped-def]
    try:
        return tuple(fn(closes, *args, **kwargs))
    except InsufficientDataError:
        return _none_series(len(closes))


def build_frame(closes: Sequence[float]) -> IndicatorFrame:
    values = tuple(float(value) for value in closes)
    n = len(values)
    if n >= MACD_MIN_BARS:
        result = macd(values)
        hist, line, signal = result.histogram, result.macd_line, result.signal_line
    else:
        hist = line = signal = _none_series(n)
    return IndicatorFrame(
        closes=values,
        sma_fast=_safe(sma, values, FAST_WINDOW),
        sma_slow=_safe(sma, values, SLOW_WINDOW),
        sma_long=_safe(sma, values, LONG_WINDOW),
        momentum=_safe(momentum, values, MOMENTUM_WINDOW),
        rsi=_safe(rsi, values, RSI_PERIOD),
        macd_hist=tuple(hist),
        macd_line=tuple(line),
        macd_signal=tuple(signal),
    )


def _clip(value: float, bound: float) -> float:
    return max(-bound, min(bound, value))


def _direction(vote: float, weight: float) -> SignalDirection:
    if vote > 0.2 * weight:
        return SignalDirection.BULLISH
    if vote < -0.2 * weight:
        return SignalDirection.BEARISH
    return SignalDirection.NEUTRAL


def _unavailable(name: str, weight: float, why: str) -> SignalReading:
    return SignalReading(name, None, SignalDirection.UNAVAILABLE, weight, 0.0, why)


def readings_at(frame: IndicatorFrame, index: int) -> tuple[SignalReading, ...]:
    """Directional readings for bar ``index`` using only data up to and including it."""

    price = frame.closes[index]
    readings: list[SignalReading] = []

    slow = frame.sma_slow[index]
    if slow is None:
        readings.append(_unavailable("trend_vs_sma50", WEIGHT_TREND_SLOW, "Fewer than 50 bars."))
    else:
        gap = price / slow - 1.0
        vote = WEIGHT_TREND_SLOW * _clip(gap / TREND_FULL_SCALE, 1.0)
        readings.append(
            SignalReading(
                "trend_vs_sma50",
                gap,
                _direction(vote, WEIGHT_TREND_SLOW),
                WEIGHT_TREND_SLOW,
                vote,
                f"Close is {gap:+.1%} versus its 50-bar average.",
            )
        )

    long = frame.sma_long[index]
    if long is None:
        readings.append(_unavailable("trend_vs_sma200", WEIGHT_TREND_LONG, "Fewer than 200 bars."))
    else:
        gap = price / long - 1.0
        vote = WEIGHT_TREND_LONG * _clip(gap / (2 * TREND_FULL_SCALE), 1.0)
        readings.append(
            SignalReading(
                "trend_vs_sma200",
                gap,
                _direction(vote, WEIGHT_TREND_LONG),
                WEIGHT_TREND_LONG,
                vote,
                f"Close is {gap:+.1%} versus its 200-bar average.",
            )
        )

    fast = frame.sma_fast[index]
    if fast is None or slow is None:
        readings.append(_unavailable("average_cross", WEIGHT_CROSS, "Needs 50 bars."))
    else:
        gap = fast / slow - 1.0
        vote = WEIGHT_CROSS * _clip(gap / TREND_FULL_SCALE, 1.0)
        readings.append(
            SignalReading(
                "average_cross",
                gap,
                _direction(vote, WEIGHT_CROSS),
                WEIGHT_CROSS,
                vote,
                f"20-bar average is {gap:+.1%} versus the 50-bar average.",
            )
        )

    mom = frame.momentum[index]
    if mom is None:
        readings.append(_unavailable("momentum_63", WEIGHT_MOMENTUM, "Fewer than 64 bars."))
    else:
        vote = WEIGHT_MOMENTUM * _clip(mom / MOMENTUM_FULL_SCALE, 1.0)
        readings.append(
            SignalReading(
                "momentum_63",
                mom,
                _direction(vote, WEIGHT_MOMENTUM),
                WEIGHT_MOMENTUM,
                vote,
                f"63-bar return is {mom:+.1%}.",
            )
        )

    hist = frame.macd_hist[index]
    if hist is None:
        readings.append(_unavailable("macd_histogram", WEIGHT_MACD, "Fewer than 35 bars."))
    else:
        relative = hist / price
        vote = WEIGHT_MACD * _clip(relative / 0.01, 1.0)
        readings.append(
            SignalReading(
                "macd_histogram",
                relative,
                _direction(vote, WEIGHT_MACD),
                WEIGHT_MACD,
                vote,
                f"MACD histogram is {relative:+.2%} of price "
                f"({'above' if hist > 0 else 'below'} its signal line).",
            )
        )

    value = frame.rsi[index]
    if value is None:
        readings.append(_unavailable("rsi_14", WEIGHT_RSI, "Fewer than 15 bars."))
    else:
        if value >= RSI_OVERBOUGHT:
            vote = -WEIGHT_RSI * _clip((value - RSI_OVERBOUGHT) / 15.0 + 0.5, 1.0)
            text = f"RSI {value:.0f} is overbought (>= {RSI_OVERBOUGHT:.0f})."
        elif value <= RSI_OVERSOLD:
            vote = WEIGHT_RSI * _clip((RSI_OVERSOLD - value) / 15.0 + 0.5, 1.0)
            text = f"RSI {value:.0f} is oversold (<= {RSI_OVERSOLD:.0f})."
        else:
            vote = 0.0
            text = f"RSI {value:.0f} is in its neutral band."
        readings.append(
            SignalReading("rsi_14", value, _direction(vote, WEIGHT_RSI), WEIGHT_RSI, vote, text)
        )
    return tuple(readings)


def aggregate_score(readings: Sequence[SignalReading]) -> tuple[float | None, float]:
    """Return (score in [-1, 1] or None, fraction of total weight that was available)."""

    total_weight = sum(r.weight for r in readings)
    used = [r for r in readings if r.direction is not SignalDirection.UNAVAILABLE]
    used_weight = sum(r.weight for r in used)
    if used_weight <= 0.0 or total_weight <= 0.0:
        return None, 0.0
    return sum(r.vote for r in used) / used_weight, used_weight / total_weight
