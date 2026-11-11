"""Time-weighted performance and drawdown from valuation points and external cash flows."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from slaifi.engines.utils.errors import EngineValidationError

MIN_DAYS_TO_ANNUALIZE = 90


@dataclass(frozen=True, slots=True)
class EquityPoint:
    """Portfolio value at ``at`` and the net external flow (deposits - withdrawals) *at* that time."""

    at: datetime
    total_value: Decimal
    net_flow: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class PerformanceSummary:
    point_count: int
    start_at: datetime | None
    end_at: datetime | None
    start_value: Decimal | None
    end_value: Decimal | None
    net_contributions: Decimal
    net_profit: Decimal | None
    time_weighted_return: float | None
    annualized_return: float | None
    max_drawdown: float | None
    current_drawdown: float | None
    index_values: tuple[float, ...]
    note: str


def summarize_performance(points: Sequence[EquityPoint]) -> PerformanceSummary:
    ordered = sorted(points, key=lambda p: p.at)
    if len(ordered) < 2:
        return PerformanceSummary(
            len(ordered),
            None,
            None,
            None,
            None,
            Decimal("0"),
            None,
            None,
            None,
            None,
            None,
            (),
            "Not enough history yet: at least two valuation points are needed.",
        )
    for point in ordered:
        if point.total_value < 0:
            raise EngineValidationError("portfolio value cannot be negative")
    index = [1.0]
    for previous, current in zip(ordered, ordered[1:], strict=False):
        base = previous.total_value
        if base <= 0:
            # No capital was at work in this sub-period: carry the index unchanged.
            index.append(index[-1])
            continue
        growth = float((current.total_value - current.net_flow) / base)
        index.append(index[-1] * growth)
    peak = index[0]
    worst = 0.0
    for value in index:
        peak = max(peak, value)
        worst = min(worst, value / peak - 1.0)
    current_dd = index[-1] / max(index) - 1.0
    contributions = sum((p.net_flow for p in ordered[1:]), Decimal("0"))
    start_value = ordered[0].total_value
    end_value = ordered[-1].total_value
    net_profit = end_value - start_value - contributions
    twr = index[-1] - 1.0
    days = (ordered[-1].at - ordered[0].at).total_seconds() / 86400.0
    annualized = None
    if days >= MIN_DAYS_TO_ANNUALIZE and index[-1] > 0:
        annualized = index[-1] ** (365.0 / days) - 1.0
    note = "Time-weighted: deposits and withdrawals do not count as performance."
    if annualized is None:
        note += f" Not annualised: history shorter than {MIN_DAYS_TO_ANNUALIZE} days."
    return PerformanceSummary(
        point_count=len(ordered),
        start_at=ordered[0].at,
        end_at=ordered[-1].at,
        start_value=start_value,
        end_value=end_value,
        net_contributions=contributions,
        net_profit=net_profit,
        time_weighted_return=twr,
        annualized_return=annualized,
        max_drawdown=worst,
        current_drawdown=current_dd,
        index_values=tuple(index),
        note=note,
    )
