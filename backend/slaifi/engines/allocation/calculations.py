"""Deterministic allocation helpers.

These functions never call an optimizer. They prepare its input from real prices and judge its
output: whatever an agent proposes, SLAIFI re-checks the weights against the strategy itself.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from slaifi.domain.strategies import RiskTolerance, StrategyProfile
from slaifi.engines.risk.calculations import concentration_hhi
from slaifi.engines.strategy import MIN_POSITIONS_FOR_HHI

PERIODS_PER_YEAR = 252
MIN_RETURN_OBSERVATIONS = 60
WEIGHT_TOLERANCE = 1e-4

# How strongly each risk tolerance leans towards past return rather than steadiness. These are
# product defaults, not fitted values; "steadiest" (0) ignores past return altogether.
_RETURN_PREFERENCE = {
    RiskTolerance.CONSERVATIVE: 0.0,
    RiskTolerance.MODERATE: 1.0,
    RiskTolerance.AGGRESSIVE: 3.0,
}


@dataclass(frozen=True, slots=True)
class AllocationCheck:
    code: str
    ok: bool
    message: str


def aligned_returns(
    closes: Mapping[str, Sequence[tuple[date, float]]],
) -> dict[str, list[float]]:
    """Simple daily returns on the dates every series has a real close (no gap is filled)."""

    if not closes:
        return {}
    by_symbol = {symbol: dict(points) for symbol, points in closes.items()}
    common = sorted(set.intersection(*(set(m) for m in by_symbol.values())))
    out: dict[str, list[float]] = {symbol: [] for symbol in closes}
    for previous, current in zip(common, common[1:], strict=False):
        for symbol, series in by_symbol.items():
            before = series[previous]
            if before <= 0:
                raise ValueError(f"{symbol} has a non-positive close on {previous}")
            out[symbol].append(series[current] / before - 1.0)
    return out


def annualised_statistics(
    returns: Mapping[str, Sequence[float]],
) -> tuple[tuple[str, ...], tuple[float, ...], tuple[tuple[float, ...], ...]]:
    """Symbols, historical mean return and covariance, both annualised (252 trading days)."""

    symbols = tuple(returns)
    lengths = {len(returns[s]) for s in symbols}
    if len(lengths) != 1:
        raise ValueError("return series must have the same length")
    n_obs = lengths.pop()
    if n_obs < 2:
        raise ValueError("at least two return observations are needed")
    mean = tuple(statistics.fmean(returns[s]) * PERIODS_PER_YEAR for s in symbols)
    cov = tuple(
        tuple(statistics.covariance(returns[a], returns[b]) * PERIODS_PER_YEAR for b in symbols)
        for a in symbols
    )
    return symbols, mean, cov


def return_preference(strategy: StrategyProfile, focus: str) -> float:
    """0 for the steadiest mix; otherwise a default that grows with the strategy's risk tolerance."""

    if focus == "steadiest":
        return 0.0
    return _RETURN_PREFERENCE.get(strategy.risk_tolerance, 0.0)


def allocation_bounds(
    strategy: StrategyProfile, count: int
) -> tuple[tuple[float, ...], tuple[float, ...], float]:
    """Per-asset lower and upper weight and the total to allocate (1 − cash reserve)."""

    cap = strategy.max_position_weight
    upper = 1.0 if cap is None else min(1.0, cap)
    budget = 1.0 - strategy.cash_reserve_rate
    return (0.0,) * count, (upper,) * count, budget


def portfolio_statistics(
    weights: Sequence[float],
    expected_returns: Sequence[float],
    covariance: Sequence[Sequence[float]],
) -> tuple[float, float]:
    """(historical annual return contribution, annualised volatility) of weights over the budget."""

    ret = sum(w * m for w, m in zip(weights, expected_returns, strict=True))
    variance = sum(
        weights[i] * covariance[i][j] * weights[j]
        for i in range(len(weights))
        for j in range(len(weights))
    )
    return ret, math.sqrt(max(variance, 0.0))


def verify_allocation(
    weights: Sequence[float],
    *,
    expected_returns: Sequence[float],
    covariance: Sequence[Sequence[float]],
    lower: Sequence[float],
    upper: Sequence[float],
    budget: float,
    strategy: StrategyProfile,
) -> tuple[AllocationCheck, ...]:
    """Judge a proposed allocation on SLAIFI's own terms. Any failed check rejects the proposal."""

    checks: list[AllocationCheck] = []
    finite = all(math.isfinite(w) for w in weights)
    checks.append(AllocationCheck("finite", finite, "Every weight is a finite number."))
    if not finite or len(weights) != len(upper):
        return tuple(checks)

    inside = all(
        lo - WEIGHT_TOLERANCE <= w <= hi + WEIGHT_TOLERANCE
        for w, lo, hi in zip(weights, lower, upper, strict=True)
    )
    largest = max(weights, default=0.0)
    checks.append(
        AllocationCheck(
            "position_bounds",
            inside,
            f"Largest position {largest:.1%} is within the strategy's {max(upper, default=1.0):.1%} cap, none negative."
            if inside
            else f"A position is outside its limits (largest {largest:.1%}, cap {max(upper, default=1.0):.1%}).",
        )
    )
    total = sum(weights)
    spent = abs(total - budget) <= 1e-3
    checks.append(
        AllocationCheck(
            "budget",
            spent,
            f"Weights add up to {total:.1%}, the amount to invest ({budget:.1%})."
            if spent
            else f"Weights add up to {total:.1%}, not the {budget:.1%} to invest.",
        )
    )
    _, volatility = portfolio_statistics(weights, expected_returns, covariance)
    # Weights are shares of the whole portfolio (cash is the remainder), so this is its volatility.
    cap = strategy.max_annualized_volatility
    if cap is None:
        checks.append(
            AllocationCheck("volatility_cap", True, "The strategy sets no volatility cap.")
        )
    else:
        within = volatility <= cap + 1e-6
        checks.append(
            AllocationCheck(
                "volatility_cap",
                within,
                f"Historical volatility {volatility:.1%} is within the strategy's {cap:.1%} cap."
                if within
                else f"Historical volatility {volatility:.1%} exceeds the strategy's {cap:.1%} cap.",
            )
        )
    hhi_cap = strategy.max_concentration_hhi
    positive = [w for w in weights if w > WEIGHT_TOLERANCE]
    if hhi_cap is None or len(positive) < MIN_POSITIONS_FOR_HHI:
        checks.append(AllocationCheck("concentration", True, "No concentration limit applies."))
    else:
        hhi = concentration_hhi(positive)
        within = hhi <= hhi_cap + 1e-6
        checks.append(
            AllocationCheck(
                "concentration",
                within,
                f"Concentration (HHI) {hhi:.3f} is within the strategy's {hhi_cap:.3f}."
                if within
                else f"Concentration (HHI) {hhi:.3f} exceeds the strategy's {hhi_cap:.3f}.",
            )
        )
    return tuple(checks)
