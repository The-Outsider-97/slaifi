"""Look-ahead-free historical simulation of the rule-based signal against buy-and-hold.

Signals at bar ``t`` use closes up to ``t``; trades fill at the **next bar's open** with the
strategy's commission and slippage. Rule thresholds are fixed product parameters (never fitted to
the data being tested), so the whole history is out-of-sample for them. The result describes the
past of one asset; it is not a forecast and is not evidence of future performance.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from slaifi.domain.market import OHLCVBar
from slaifi.domain.strategies import StrategyProfile
from slaifi.engines.recommendation.rules import thresholds_for
from slaifi.engines.recommendation.signals import aggregate_score, build_frame, readings_at
from slaifi.engines.technical import normalize_bars
from slaifi.engines.utils.errors import InsufficientDataError

MIN_BARS = 252
WARMUP_BARS = 64
BARS_PER_YEAR = 252


@dataclass(frozen=True, slots=True)
class BacktestTrade:
    entered_at: datetime
    exited_at: datetime | None
    entry_price: float
    exit_price: float | None
    return_rate: float | None


@dataclass(frozen=True, slots=True)
class BacktestResult:
    strategy_id: str
    bar_count: int
    start_at: datetime
    end_at: datetime
    total_return: float
    annualized_return: float | None
    max_drawdown: float
    exposure_rate: float
    trade_count: int
    win_rate: float | None
    benchmark_total_return: float
    benchmark_annualized_return: float | None
    benchmark_max_drawdown: float
    excess_return: float
    first_half_return: float
    second_half_return: float
    commission_rate: float
    slippage_rate: float
    trades: tuple[BacktestTrade, ...]
    assumptions: tuple[str, ...]


def _max_drawdown(values: Sequence[float]) -> float:
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        worst = min(worst, value / peak - 1.0)
    return worst


def _annualize(total_return: float, bar_count: int) -> float | None:
    if bar_count < BARS_PER_YEAR or total_return <= -1.0:
        return None
    return float((1.0 + total_return) ** (BARS_PER_YEAR / bar_count) - 1.0)


def run_backtest(bars: Sequence[OHLCVBar], strategy: StrategyProfile) -> BacktestResult:  # noqa: C901
    ordered, _, _ = normalize_bars(list(bars))
    if len(ordered) < MIN_BARS:
        raise InsufficientDataError(
            f"a backtest needs at least {MIN_BARS} daily bars; got {len(ordered)}"
        )
    closes = [float(b.close) for b in ordered]
    opens = [float(b.open) for b in ordered]
    frame = build_frame(closes)
    thresholds = thresholds_for(strategy)
    commission = float(strategy.costs.commission_rate)
    slippage = float(strategy.costs.slippage_rate)

    equity = 1.0
    units = 0.0
    entry_open = 0.0
    entered_at: datetime | None = None
    in_market_bars = 0
    curve: list[float] = []
    trades: list[BacktestTrade] = []
    pending: str | None = None  # "enter" | "exit", decided at previous close
    start_index = WARMUP_BARS

    for t in range(start_index, len(ordered)):
        # 1. fill the order decided at the previous close, at this bar's open
        if pending == "enter" and units == 0.0:
            fill = opens[t] * (1.0 + slippage)
            units = equity * (1.0 - commission) / fill
            entry_open = fill
            entered_at = ordered[t].start_at
            equity = 0.0
        elif pending == "exit" and units > 0.0:
            fill = opens[t] * (1.0 - slippage)
            equity = units * fill * (1.0 - commission)
            trades.append(
                BacktestTrade(
                    entered_at or ordered[t].start_at,
                    ordered[t].start_at,
                    entry_open,
                    fill,
                    fill / entry_open - 1.0,
                )
            )
            units = 0.0
        pending = None
        # 2. mark to market at the close
        marked = equity + units * closes[t]
        curve.append(marked)
        if units > 0.0:
            in_market_bars += 1
        # 3. decide for the next bar using information up to and including this close
        score, coverage = aggregate_score(readings_at(frame, t))
        if score is None or coverage < thresholds.min_weight_coverage:
            continue
        if units == 0.0 and score >= thresholds.buy:
            pending = "enter"
        elif units > 0.0 and score <= thresholds.reduce:
            pending = "exit"

    if units > 0.0:
        trades.append(
            BacktestTrade(
                entered_at or ordered[-1].start_at,
                None,
                entry_open,
                None,
                closes[-1] / entry_open - 1.0,
            )
        )
    n = len(curve)
    total = curve[-1] / 1.0 - 1.0
    mid = n // 2
    first_half = curve[mid - 1] - 1.0
    second_half = curve[-1] / curve[mid - 1] - 1.0

    # buy-and-hold over the same bars: buy at the first tradable open, pay costs both ends
    bh_units = (1.0 - commission) / (opens[start_index] * (1.0 + slippage))
    bh_curve = [bh_units * closes[t] for t in range(start_index, len(ordered))]
    bh_total = bh_curve[-1] * (1.0 - slippage) * (1.0 - commission) - 1.0
    closed = [t for t in trades if t.return_rate is not None and t.exited_at is not None]
    wins = sum(1 for t in closed if (t.return_rate or 0.0) > 0.0)
    return BacktestResult(
        strategy_id=strategy.strategy_id,
        bar_count=n,
        start_at=ordered[start_index].start_at,
        end_at=ordered[-1].end_at,
        total_return=total,
        annualized_return=_annualize(total, n),
        max_drawdown=_max_drawdown(curve),
        exposure_rate=in_market_bars / n,
        trade_count=len(trades),
        win_rate=(wins / len(closed)) if closed else None,
        benchmark_total_return=bh_total,
        benchmark_annualized_return=_annualize(bh_total, n),
        benchmark_max_drawdown=_max_drawdown(bh_curve),
        excess_return=total - bh_total,
        first_half_return=first_half,
        second_half_return=second_half,
        commission_rate=commission,
        slippage_rate=slippage,
        trades=tuple(trades),
        assumptions=(
            "Signals use data up to each close; fills occur at the next bar's open.",
            f"Costs per side: commission {commission:.4%} and slippage {slippage:.4%} of notional.",
            "Long-only, fully invested or in cash; rule thresholds are fixed, not optimised on this data.",
            "Dividends and taxes are not modelled; prices are as supplied by the data provider.",
            "A historical simulation of one asset is not a forecast and not evidence of future results.",
        ),
    )


def _dec(value: float) -> Decimal:
    return Decimal(repr(value))
