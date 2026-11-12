"""Empirical-quantile return interval with walk-forward coverage validation.

The only forecast SLAIFI emits is an *interval* of historical horizon returns for one asset,
and only after it has been tested out-of-sample on that asset's own history:

* at each test origin the interval is built from horizon returns that were fully realised
  *before* the origin (no look-ahead);
* test origins are spaced one horizon apart so outcomes do not overlap;
* the interval is released only if enough independent tests exist and realised coverage is
  statistically compatible with the nominal coverage.

The model is deliberately simple. It assumes the recent distribution of horizon returns is
informative about the next horizon, which can fail at regime changes. No probability, expected
return or accuracy beyond the measured coverage is ever invented.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from slaifi.engines.utils import positive_series, require_positive_integer
from slaifi.engines.utils.errors import EngineValidationError

MODEL_NAME = "empirical_quantile_interval"
MODEL_VERSION = "1.0.0"
NOMINAL_COVERAGE = 0.80
MIN_TRAIN_RETURNS = 120
MIN_TEST_ORIGINS = 20
BARS_PER_YEAR = 252
MIN_BARS_PER_HORIZON = 5
MAX_HORIZON_BARS = 252


@dataclass(frozen=True, slots=True)
class IntervalEstimate:
    lower: float
    median: float
    upper: float
    nominal_coverage: float
    sample_size: int


@dataclass(frozen=True, slots=True)
class CoverageValidation:
    nominal_coverage: float
    realized_coverage: float | None
    test_count: int
    mean_interval_width: float | None
    tolerance: float | None
    passed: bool
    note: str


def horizon_bars_for_days(horizon_days: int) -> int:
    """Convert a calendar-day horizon to trading bars (daily bars, 252/365 convention)."""

    require_positive_integer(horizon_days, name="horizon_days")
    return max(1, round(horizon_days * BARS_PER_YEAR / 365))


def quantile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolated quantile of an already sorted sequence."""

    if not sorted_values:
        raise EngineValidationError("quantile of an empty sequence")
    if not 0.0 <= q <= 1.0:
        raise EngineValidationError("q must be in [0, 1]")
    position = q * (len(sorted_values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    fraction = position - lower
    return sorted_values[lower] * (1.0 - fraction) + sorted_values[upper] * fraction


def horizon_returns(
    closes: Sequence[float], horizon: int, *, end: int | None = None
) -> list[float]:
    """Overlapping simple returns p[s+h]/p[s]-1 for every s with s+h <= end (inclusive index)."""

    last = len(closes) - 1 if end is None else end
    return [closes[s + horizon] / closes[s] - 1.0 for s in range(0, last - horizon + 1)]


def estimate_interval(
    returns: Sequence[float], *, nominal_coverage: float = NOMINAL_COVERAGE
) -> IntervalEstimate:
    if not 0.0 < nominal_coverage < 1.0:
        raise EngineValidationError("nominal_coverage must be in (0, 1)")
    ordered = sorted(returns)
    tail = (1.0 - nominal_coverage) / 2.0
    return IntervalEstimate(
        lower=quantile(ordered, tail),
        median=quantile(ordered, 0.5),
        upper=quantile(ordered, 1.0 - tail),
        nominal_coverage=nominal_coverage,
        sample_size=len(ordered),
    )


def validate_walk_forward(
    closes: Sequence[float],
    horizon: int,
    *,
    nominal_coverage: float = NOMINAL_COVERAGE,
    min_train: int = MIN_TRAIN_RETURNS,
    min_tests: int = MIN_TEST_ORIGINS,
) -> CoverageValidation:
    """Out-of-sample coverage test of the interval model on this series."""

    data = positive_series(closes, minimum=2, name="closes")
    require_positive_integer(horizon, name="horizon")
    hits = 0
    tests = 0
    widths: list[float] = []
    origin = min_train + horizon  # first origin with >= min_train realised horizon returns
    while origin + horizon <= len(data) - 1:
        train = horizon_returns(data, horizon, end=origin)  # outcomes known by `origin`
        estimate = estimate_interval(train, nominal_coverage=nominal_coverage)
        outcome = data[origin + horizon] / data[origin] - 1.0
        tests += 1
        hits += int(estimate.lower <= outcome <= estimate.upper)
        widths.append(estimate.upper - estimate.lower)
        origin += horizon
    if tests < min_tests:
        return CoverageValidation(
            nominal_coverage,
            None,
            tests,
            None,
            None,
            False,
            f"Only {tests} independent out-of-sample tests are possible for this horizon "
            f"(at least {min_tests} are required), so no forecast is released.",
        )
    realized = hits / tests
    tolerance = 2.0 * math.sqrt(nominal_coverage * (1.0 - nominal_coverage) / tests)
    passed = realized >= nominal_coverage - tolerance
    note = (
        f"Realised coverage {realized:.0%} over {tests} independent tests versus "
        f"{nominal_coverage:.0%} nominal (tolerance ±{tolerance:.0%})."
    )
    if not passed:
        note += " The interval under-covered outcomes, so it is not released as a forecast."
    return CoverageValidation(
        nominal_coverage,
        realized,
        tests,
        sum(widths) / len(widths),
        tolerance,
        passed,
        note,
    )
