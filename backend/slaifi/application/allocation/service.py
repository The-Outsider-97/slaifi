"""Suggest a steadier mix of holdings, within the strategy's limits.

This is advice built from real price history. SLAI's Financial agent (which solves through SLAI's
Optimization agent) proposes weights; SLAIFI re-checks them against the strategy and shows the
result next to the current mix. Nothing is ordered here: the person decides, and any order still
goes through the normal checks.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from slaifi.application.contracts import (
    AllocationProblem,
    FinanceStore,
    FinancialAnalyst,
    PriceSeries,
)
from slaifi.application.market import MarketDataService
from slaifi.application.paper import PaperTradingService
from slaifi.application.strategies import StrategyService
from slaifi.core.utils.errors import ConflictError, NotFoundError, SlaifiError
from slaifi.domain.assets import AssetId
from slaifi.domain.portfolio import TradeSide
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
# A change smaller than this share of the portfolio is not worth an order (and its fee).
MIN_CHANGE = 0.005
PLAN_TTL = timedelta(minutes=15)
MAX_PLANS = 50


@dataclass(frozen=True, slots=True)
class AllocationLine:
    symbol: str
    display: str
    current_weight: float
    suggested_weight: float
    change: float
    amount: Decimal | None  # money to move to reach the suggested weight (+ buy, − sell)
    side: str | None = None  # "buy" / "sell" when an order would be placed, else None (no change)


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
    agent_notes: tuple[str, ...] = ()
    suggestion_id: str | None = None  # what Apply refers to; the orders are rebuilt from it here
    expires_at: datetime | None = None
    fee_per_trade: Decimal | None = None
    plan_notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _PlannedOrder:
    asset: AssetId
    display: str
    side: TradeSide
    notional: Decimal | None
    close_position: bool


@dataclass(slots=True)
class _Plan:
    """What a suggestion would trade. Kept here so Apply never relies on amounts from the browser."""

    portfolio_id: str
    expires_at: datetime
    marker: tuple[int, int]
    orders: dict[str, _PlannedOrder]
    done: set[str] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class AppliedOrder:
    """``status``: ``filled`` · ``rejected`` · ``already_applied``."""

    symbol: str
    display: str
    side: str
    status: str
    detail: str | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    fee: Decimal | None = None


@dataclass(frozen=True, slots=True)
class AppliedAllocation:
    suggestion_id: str
    orders: tuple[AppliedOrder, ...]

    @property
    def filled(self) -> int:
        return sum(1 for o in self.orders if o.status == "filled")

    @property
    def fees(self) -> Decimal:
        return sum((o.fee or Decimal(0) for o in self.orders if o.status == "filled"), Decimal(0))


class AllocationService:
    def __init__(
        self,
        paper: PaperTradingService,
        strategies: StrategyService,
        market: MarketDataService,
        store: FinanceStore,
        analyst: FinancialAnalyst,
        *,
        enabled: Callable[[], bool],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._paper = paper
        self._strategies = strategies
        self._market = market
        self._store = store
        self._analyst = analyst
        self._enabled = enabled
        self._clock = clock or (lambda: datetime.now(UTC))
        self._plans: OrderedDict[str, _Plan] = OrderedDict()
        self._apply_lock = asyncio.Lock()

    # ------------------------------------------------------------------ apply
    def _marker(self, portfolio_id: str) -> tuple[int, int]:
        """Trades and cash movements so far: if it changes, the suggested amounts are out of date."""

        try:
            return (
                len(self._store.list_trades(portfolio_id)),
                len(self._store.list_cash_flows(portfolio_id)),
            )
        except KeyError:  # not a portfolio: the caller's next step reports that properly
            return (0, 0)

    def _remember(self, plan: _Plan) -> str:
        now = self._clock()
        for key in [k for k, p in self._plans.items() if p.expires_at <= now]:
            del self._plans[key]
        suggestion_id = f"S-{uuid.uuid4().hex[:12]}"
        self._plans[suggestion_id] = plan
        while len(self._plans) > MAX_PLANS:
            self._plans.popitem(last=False)
        return suggestion_id

    async def apply(
        self, portfolio_id: str, suggestion_id: str, symbols: tuple[str, ...] | None = None
    ) -> AppliedAllocation:
        """Place the paper orders for a suggestion: all of them, or only ``symbols``.

        Sells go first so their cash is there for the buys. Every order goes through the normal
        paper-trading path (fresh quote, strategy limits, platform fees); one being refused does
        not stop the others. Sending the same request twice places nothing twice.
        """

        async with self._apply_lock:
            plan = self._plans.get(suggestion_id)
            if (
                plan is None
                or plan.portfolio_id != portfolio_id
                or plan.expires_at <= self._clock()
            ):
                raise NotFoundError(
                    "That suggestion has expired or no longer exists. Ask for a new one."
                )
            if self._marker(portfolio_id) != plan.marker:
                raise ConflictError(
                    "The portfolio has changed since this suggestion was made, so its amounts "
                    "are out of date. Ask for a new one."
                )
            wanted = list(plan.orders) if symbols is None else [s.upper() for s in symbols]
            chosen = {s.upper(): s for s in plan.orders}
            unknown = [s for s in wanted if s not in chosen]
            if unknown:
                raise NotFoundError(
                    f"{', '.join(unknown)} has nothing to apply in this suggestion."
                )
            ordered = sorted(
                (chosen[s] for s in dict.fromkeys(wanted)),
                key=lambda s: plan.orders[s].side is not TradeSide.SELL,
            )
            # Concentration is judged on the finished mix, which SLAIFI checked when it made the
            # suggestion, only when every remaining order of the suggestion is being placed.
            complete = set(plan.orders) - plan.done <= set(ordered)
            results: list[AppliedOrder] = []
            for key in ordered:
                order = plan.orders[key]
                if key in plan.done:
                    results.append(
                        AppliedOrder(key, order.display, order.side.value, "already_applied")
                    )
                    continue
                outcome = await self._paper.place_order(
                    portfolio_id,
                    symbol=order.asset.symbol,
                    side=order.side,
                    notional=order.notional,
                    close_position=order.close_position,
                    client_order_id=f"alloc-{suggestion_id}-{key}"[:80],
                    exchange=order.asset.exchange,
                    asset_class=order.asset.asset_class,
                    whole_mix_verified=complete,
                )
                decision = outcome.decision
                if decision.trade is not None and decision.execution is not None:
                    plan.done.add(key)
                    results.append(
                        AppliedOrder(
                            key,
                            order.display,
                            order.side.value,
                            "filled",
                            quantity=decision.trade.quantity,
                            price=decision.execution.execution_price,
                            fee=decision.trade.fee,
                        )
                    )
                else:
                    reason = "; ".join(r.message for r in decision.rejections) or "Order refused."
                    results.append(
                        AppliedOrder(key, order.display, order.side.value, "rejected", reason)
                    )
            plan.marker = self._marker(portfolio_id)
            self._store.append_audit(
                at=self._clock(),
                actor="user",
                action="paper.allocation.applied",
                subject=portfolio_id,
                detail={
                    "suggestion_id": suggestion_id,
                    "symbols": [r.symbol for r in results],
                    "filled": sum(1 for r in results if r.status == "filled"),
                    "rejected": sum(1 for r in results if r.status == "rejected"),
                },
            )
            return AppliedAllocation(suggestion_id, tuple(results))

    async def suggest(
        self,
        portfolio_id: str,
        *,
        symbols: tuple[str, ...] = (),
        include_watchlist: bool = False,
        focus: str = "steadiest",
    ) -> AllocationSuggestion:
        marker = self._marker(portfolio_id)
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
            return result("disabled", "The Financial agent is switched off in Settings.")

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
        real: dict[str, PriceSeries] = {}

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
            exact = [(b.start_at.date(), b.close) for b in view_.bars if b.close > 0]
            series = [(day, float(close)) for day, close in exact]
            if len(series) < MIN_RETURN_OBSERVATIONS + 1:
                excluded.append((asset.display_symbol, "NOT AVAILABLE: too little price history."))
                return
            closes[symbol] = series
            real[symbol] = PriceSeries(
                symbol,
                tuple(exact),
                view_.provenance.source or "market data",
                str(asset.currency or view.portfolio.base_currency),
            )

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
        # The agent is given exactly the closes the statistics were built from: the dates on which
        # every asset has a real close, so nothing is filled in.
        common_days = set.intersection(*(set(d for d, _ in closes[n]) for n in names))
        series = tuple(
            PriceSeries(
                real[n].symbol,
                tuple((d, c) for d, c in real[n].closes if d in common_days),
                real[n].source,
                real[n].currency,
            )
            for n in names
        )
        problem = AllocationProblem(
            names,
            mean,
            cov,
            lower,
            upper,
            budget,
            return_preference(strategy, focus),
            series,
        )
        solved = await asyncio.to_thread(self._analyst.solve, problem)
        window = [pt[0] for pt in closes[names[0]]]
        common = dict(
            excluded=tuple(excluded),
            observations=observations,
            window_start=window[0],
            window_end=window[-1],
            solver=solved.solver,
            agent_notes=solved.warnings,
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
        rows: list[tuple[str, float, float, Decimal | None, TradeSide | None]] = []
        for s, w in zip(names, weights, strict=True):
            change = w - current[s]
            amount = (Decimal(str(change)) * total).quantize(Decimal("0.01")) if total > 0 else None
            side: TradeSide | None = None
            if amount is not None and abs(change) >= MIN_CHANGE and abs(amount) >= Decimal("1"):
                side = TradeSide.BUY if change > 0 else TradeSide.SELL
            rows.append((s, w, change, amount, side))

        # Every order pays the platform's flat fee (plus the strategy's proportional commission) and
        # a sale receives a little less than its mark because of slippage. The suggested weights do
        # not know about these costs, so trim the buys by them (the part that would eat into the
        # cash reserve) rather than have the last order refused for leaving too little cash.
        fee = self._paper.platform_fees().per_trade
        costs = strategy.costs
        order_count = sum(1 for r in rows if r[4] is not None)
        buy_total = sum((r[3] for r in rows if r[4] is TradeSide.BUY and r[3]), Decimal(0))
        sell_total = sum((-r[3] for r in rows if r[4] is TradeSide.SELL and r[3]), Decimal(0))
        trim = Decimal(0)
        notes: list[str] = []
        if order_count and buy_total > 0:
            fees_total = fee * order_count + costs.commission_rate * (buy_total + sell_total)
            keep = Decimal(str(1 - strategy.cash_reserve_rate))
            trim = min(
                (fees_total * keep + costs.slippage_rate * sell_total + Decimal("0.01")).quantize(
                    Decimal("0.01")
                ),
                buy_total / 2,
            )
            if fees_total > 0:
                notes.append(
                    f"The {order_count} order(s) cost about {fees_total:.2f} in fees; the buys are "
                    f"reduced by {trim:.2f} in total so the cash reserve still holds afterwards."
                )
        factor = (buy_total - trim) / buy_total if buy_total > 0 else Decimal(1)

        lines_: list[AllocationLine] = []
        planned: dict[str, _PlannedOrder] = {}
        for s, w, change, amount, side in rows:
            if amount is not None and side is TradeSide.BUY:
                amount = (amount * factor).quantize(Decimal("0.01"))
            if side is not None and amount is not None:
                closing = side is TradeSide.SELL and w < 1e-6
                planned[s.upper()] = _PlannedOrder(
                    usable[s],
                    usable[s].display_symbol,
                    side,
                    None if closing else abs(amount),
                    closing,
                )
            lines_.append(
                AllocationLine(
                    symbol=s,
                    display=usable[s].display_symbol,
                    current_weight=current[s],
                    suggested_weight=w,
                    change=change,
                    amount=amount,
                    side=side.value if side else None,
                )
            )
        lines = tuple(lines_)
        now = self._clock()
        expires = now + PLAN_TTL
        suggestion_id = (
            self._remember(_Plan(portfolio_id, expires, marker, planned)) if planned else None
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
            suggestion_id=suggestion_id,
            expires_at=expires if suggestion_id else None,
            fee_per_trade=fee,
            plan_notes=tuple(notes),
            **common,
        )
