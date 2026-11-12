"""Suggest a steadier mix of holdings, within the strategy's limits.

This is advice built from real price history. The optimizer (SLAI's Optimization agent) proposes
weights; SLAIFI re-checks them against the strategy and shows the result next to the current mix.
Nothing is ordered: the person decides, and any order still goes through the normal checks.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from slaifi.application.contracts import (
    AllocationProblem,
    FinanceStore,
    PortfolioOptimizer,
)
from slaifi.application.market import MarketDataService
from slaifi.application.paper import PaperTradingService
from slaifi.application.strategies import StrategyService
from slaifi.core.utils.errors import SlaifiError
from slaifi.domain.assets import AssetId
from slaifi.engines.allocation import (
    MIN_RETURN_OBSERVATIONS,
    AllocationCheck,
    aligned_returns,
    allocation_bounds,
    annualised_statistics,
    portfolio_statistics,
    return_preference,
    verify_allocation,
)
from slaifi.engines.strategy import asset_eligibility

MAX_ASSETS = 20
HISTORY_DAYS = 420
FOCUSES = ("steadiest", "strategy")


@dataclass(frozen=True, slots=True)
class AllocationLine:
    symbol: str
    display: str
    current_weight: float
    suggested_weight: float
    change: float
    amount: Decimal | None  # money to move to reach the suggested weight (+ buy, − sell)


@dataclass(frozen=True, slots=True)
class AllocationStats:
    annual_volatility: float | None
    historical_annual_return: float | None


@dataclass(frozen=True, slots=True)
class AllocationSuggestion:
    """``status``: ``ok`` · ``rejected`` (the proposal broke a limit) · ``infeasible`` ·
    ``insufficient_data`` · ``unavailable`` · ``disabled``."""

    status: str
    detail: str | None
    portfolio_id: str
    strategy_id: str
    focus: str
    lines: tuple[AllocationLine, ...] = ()
    excluded: tuple[tuple[str, str], ...] = ()
    current: AllocationStats | None = None
    suggested: AllocationStats | None = None
    checks: tuple[AllocationCheck, ...] = ()
    solver: str | None = None
    observations: int = 0
    window_start: date | None = None
    window_end: date | None = None
    cash_weight: float | None = None
    generated_at: datetime | None = None


class AllocationService:
    def __init__(
        self,
        paper: PaperTradingService,
        strategies: StrategyService,
        market: MarketDataService,
        store: FinanceStore,
        optimizer: PortfolioOptimizer,
        *,
        enabled: Callable[[], bool],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._paper = paper
        self._strategies = strategies
        self._market = market
        self._store = store
        self._optimizer = optimizer
        self._enabled = enabled
        self._clock = clock or (lambda: datetime.now(UTC))

    async def suggest(
        self,
        portfolio_id: str,
        *,
        symbols: tuple[str, ...] = (),
        include_watchlist: bool = False,
        focus: str = "steadiest",
    ) -> AllocationSuggestion:
        view = await self._paper.view(portfolio_id, record=False)
        strategy = self._paper.strategy_for(view.portfolio)

        def result(status: str, detail: str | None, **kw: object) -> AllocationSuggestion:
            return AllocationSuggestion(
                status,
                detail,
                portfolio_id,
                strategy.strategy_id,
                focus,
                generated_at=self._clock(),
                **kw,  # type: ignore[arg-type]
            )

        if focus not in FOCUSES:
            focus = "steadiest"
        if not self._enabled():
            return result("disabled", "The Optimization agent is switched off in Settings.")

        total = view.snapshot.total_value
        excluded: list[tuple[str, str]] = []
        universe: dict[str, AssetId] = {}
        held_value: dict[str, Decimal] = {}
        for position in view.positions:
            valuation = position.valuation
            asset = valuation.position.asset
            if valuation.position.quantity < 0:
                excluded.append(
                    (asset.display_symbol, "A short position: not part of this suggestion.")
                )
                continue
            universe[asset.symbol] = asset
            held_value[asset.symbol] = valuation.market_value
        extra = list(symbols)
        if include_watchlist:
            extra += [item.asset.symbol for item in self._store.list_watchlist()]
        for text in extra:
            if len(universe) >= MAX_ASSETS:
                excluded.append((text.upper(), f"Only {MAX_ASSETS} assets are considered at once."))
                continue
            try:
                asset = await self._market.resolve_asset(text)
            except SlaifiError as exc:
                excluded.append((text.upper(), f"Not recognised: {exc.message}"))
                continue
            universe.setdefault(asset.symbol, asset)

        # Strategy limits that rule an asset out altogether.
        candidates: dict[str, AssetId] = {}
        for symbol, asset in universe.items():
            blocking = [f for f in asset_eligibility(asset, strategy) if f.severity == "hard"]
            if blocking:
                excluded.append((asset.display_symbol, blocking[0].message))
            else:
                candidates[symbol] = asset

        closes: dict[str, list[tuple[date, float]]] = {}

        async def history(symbol: str, asset: AssetId) -> None:
            try:
                view_ = await self._market.history(asset, days=HISTORY_DAYS)
            except SlaifiError as exc:
                excluded.append((asset.display_symbol, f"NOT AVAILABLE: {exc.message}"))
                return
            if view_.provenance.last_known:
                excluded.append(
                    (asset.display_symbol, "NOT AVAILABLE: only saved (last known) prices exist.")
                )
                return
            series = [(b.start_at.date(), float(b.close)) for b in view_.bars if b.close > 0]
            if len(series) < MIN_RETURN_OBSERVATIONS + 1:
                excluded.append((asset.display_symbol, "NOT AVAILABLE: too little price history."))
                return
            closes[symbol] = series

        await asyncio.gather(*(history(s, a) for s, a in candidates.items()))
        usable = {s: candidates[s] for s in candidates if s in closes}
        held_dropped = [s for s in held_value if s not in usable]
        excluded = sorted(set(excluded))
        if len(usable) < 2:
            return result(
                "insufficient_data",
                "At least two assets with real price history are needed to suggest a mix.",
                excluded=tuple(excluded),
            )

        returns = aligned_returns({s: closes[s] for s in usable})
        observations = len(next(iter(returns.values())))
        if observations < MIN_RETURN_OBSERVATIONS:
            return result(
                "insufficient_data",
                f"Only {observations} trading days have prices for every asset; at least "
                f"{MIN_RETURN_OBSERVATIONS} are needed.",
                excluded=tuple(excluded),
                observations=observations,
            )
        names, mean, cov = annualised_statistics(returns)
        lower, upper, budget = allocation_bounds(strategy, len(names))
        if sum(upper) < budget - 1e-9:
            need = int(-(-budget // upper[0])) if upper[0] > 0 else len(names)
            return result(
                "infeasible",
                f"With a {upper[0]:.0%} cap per position and {budget:.0%} to invest, at least "
                f"{need} assets are needed; {len(names)} had usable history.",
                excluded=tuple(excluded),
                observations=observations,
            )
        problem = AllocationProblem(
            names, mean, cov, lower, upper, budget, return_preference(strategy, focus)
        )
        solved = await asyncio.to_thread(self._optimizer.solve, problem)
        window = [pt[0] for pt in closes[names[0]]]
        common = dict(
            excluded=tuple(excluded),
            observations=observations,
            window_start=window[0],
            window_end=window[-1],
            solver=solved.solver,
        )
        if solved.status != "ok" or solved.weights is None:
            status = (
                solved.status
                if solved.status in ("disabled", "unavailable", "infeasible")
                else "unavailable"
            )
            return result(status, solved.detail, **common)

        weights = tuple(0.0 if abs(w) < 1e-6 else w for w in solved.weights)
        checks = verify_allocation(
            weights,
            expected_returns=mean,
            covariance=cov,
            lower=lower,
            upper=upper,
            budget=budget,
            strategy=strategy,
        )
        failed = [c for c in checks if not c.ok]
        if failed:
            return result(
                "rejected",
                "SLAIFI did not accept the proposal: " + " ".join(c.message for c in failed),
                checks=checks,
                **common,
            )

        current = {
            s: (float(held_value[s] / total) if total > 0 and s in held_value else 0.0)
            for s in names
        }
        lines = tuple(
            AllocationLine(
                symbol=s,
                display=usable[s].display_symbol,
                current_weight=current[s],
                suggested_weight=w,
                change=w - current[s],
                amount=(Decimal(str(w - current[s])) * total).quantize(Decimal("0.01"))
                if total > 0
                else None,
            )
            for s, w in zip(names, weights, strict=True)
        )
        current_vector = [current[s] for s in names]
        if held_dropped or sum(current_vector) <= 0:
            current_stats = None  # a holding without usable history would make this misleading
        else:
            ret, vol = portfolio_statistics(current_vector, mean, cov)
            current_stats = AllocationStats(vol, ret)
        s_ret, s_vol = portfolio_statistics(weights, mean, cov)
        detail = None
        if held_dropped:
            detail = (
                "Some holdings have no usable price history, so the current mix is not compared."
            )
        return result(
            "ok",
            detail,
            lines=lines,
            current=current_stats,
            suggested=AllocationStats(s_vol, s_ret),
            checks=checks,
            cash_weight=1.0 - sum(weights),
            **common,
        )
