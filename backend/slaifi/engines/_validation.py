"""Shared lower-layer validation helpers for numerical engines."""

from collections.abc import Sequence
from math import isfinite

from slaifi.core.exceptions import InsufficientDataError, ValidationError
from slaifi.domain.market import OHLCVBar


def finite_series(values: Sequence[float], *, minimum: int = 1, name: str = "series") -> tuple[float, ...]:
    if len(values) < minimum:
        raise InsufficientDataError(f"{name} requires at least {minimum} observations")
    normalized = tuple(float(value) for value in values)
    if not all(isfinite(value) for value in normalized):
        raise ValidationError(f"{name} contains NaN or infinity")
    return normalized


def positive_series(values: Sequence[float], *, minimum: int = 1, name: str = "series") -> tuple[float, ...]:
    normalized = finite_series(values, minimum=minimum, name=name)
    if any(value <= 0.0 for value in normalized):
        raise ValidationError(f"{name} must contain only positive values")
    return normalized


def chronological_bars(bars: Sequence[OHLCVBar], *, minimum: int = 1) -> tuple[OHLCVBar, ...]:
    if len(bars) < minimum:
        raise InsufficientDataError(f"bar series requires at least {minimum} observations")
    normalized = tuple(bars)
    previous_end = None
    for bar in normalized:
        if previous_end is not None and bar.end_at <= previous_end:
            raise ValidationError("bars must be strictly ordered with unique end timestamps")
        previous_end = bar.end_at
    return normalized
