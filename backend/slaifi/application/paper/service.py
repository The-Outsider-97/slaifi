"""Paper-trading application service.

The ledger in the store is the single source of truth. This service never keeps its own copy of
holdings or cash: every view is *derived* from the ledger by the portfolio engines. Orders are
priced from provider quotes that are validated for freshness, currency, market status and
whether they are current (a last-known price is never executable); the simulated fill (with slippage and commission) is recorded separately from
the quotation. Real-money trading does not exist anywhere in this code base.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from slaifi.application.contracts import (
    FinanceStore,
    ReconciliationIssue,
    ReconciliationReport,
)
from slaifi.application.market import MarketDataService, QuoteView
from slaifi.application.strategies import StrategyService
from slaifi.core.types import CurrencyCode
from slaifi.core.utils.errors import (
    ConflictError,
    MarketDataError,
    NotFoundError,
    SlaifiError,
    ValidationError,
)
from slaifi.domain.assets import AssetClass, AssetId
from slaifi.domain.ledger import ValuationPoint
from slaifi.domain.paper import (
    ExecutionPolicy,
    OrderDecision,
    OrderRequest,
    OrderStatus,
    PaperPortfolio,
    Rejection,
    RejectionCode,
)
from slaifi.domain.portfolio import (
    CashFlow,
    CashFlowKind,
    Portfolio,
    PortfolioSnapshot,
    PositionValuation,
    TradeSide,
)
from slaifi.domain.strategies import StrategyProfile
from slaifi.engines.features import simple_returns
from slaifi.engines.paper import evaluate_order
from slaifi.engines.portfolio import (
    EquityPoint,
    PerformanceSummary,
    build_positions,
    summarize_performance,
    value_portfolio,
)
from slaifi.engines.risk import historical_volatility

MAX_AMOUNT = Decimal("1000000000000")
_CENT = Decimal("0.01")
_ZERO = Decimal("0")
VIEW_RECORD_INTERVAL_SECONDS = 900


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _money(value: Decimal, name: str) -> Decimal:
    if not value.is_finite() or value <= 0:
        raise ValidationError(f"{name} must be a positive number")
    if value > MAX_AMOUNT:
        raise ValidationError(f"{name} is too large")
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class PositionView:
    valuation: PositionValuation
    price_basis: str  # quote | last_known | last_fill
    stale: bool
    quote: QuoteView | None
    asset_class: str


@dataclass(frozen=True, slots=True)
class PortfolioView:
    portfolio: PaperPortfolio
    snapshot: PortfolioSnapshot
    positions: tuple[PositionView, ...]
    as_of: datetime
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    fees_paid: Decimal
    slippage_cost: Decimal
    net_contributions: Decimal
    total_pnl: Decimal
    simple_return: float | None
    valuation_complete: bool
    strategy_id: str | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OrderOutcome:
    decision: OrderDecision
    asset: AssetId
    duplicate: bool
    dry_run: bool
    portfolio: PortfolioView | None
    strategy_id: str | None


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    at: datetime
    kind: str  # trade | deposit | withdrawal | initial | rejection | reset
    summary: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PerformanceView:
    portfolio_id: str
    summary: PerformanceSummary
    equity_curve: tuple[tuple[datetime, Decimal], ...]
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    net_contributions: Decimal
    simple_return: float | None
    fees_paid: Decimal
    slippage_cost: Decimal
    exposure: float | None
    cash_weight: float | None
    largest_position_weight: float | None
    concentration_hhi: float | None
    notes: tuple[str, ...]


class PaperTradingService:
    """Create, fund, trade, value, audit and reset simulated portfolios."""

    def __init__(
        self,
        store: FinanceStore,
        market: MarketDataService,
        strategies: StrategyService,
        *,
        policy: ExecutionPolicy | None = None,
        clock: Callable[[], datetime] = _utc_now,
        storage_status: str = "ok",
    ) -> None:
        self._store = store
        self._market = market
        self._strategies = strategies
        self._policy = policy or ExecutionPolicy()
        self._clock = clock
        self._lock = asyncio.Lock()
        self._storage_status = storage_status

    # ------------------------------------------------------------------ guards
    def _require_storage(self) -> None:
        if self._storage_status != "ok":
            raise ConflictError(
                "The ledger failed its integrity check, so trading is disabled until it is "
                f"restored from a backup ({self._storage_status}).",
            )

    def _require(self, portfolio_id: str) -> PaperPortfolio:
        found = self._store.get_portfolio(portfolio_id)
        if found is None:
            raise NotFoundError(f"portfolio {portfolio_id!r} does not exist")
        return found

    def strategy_for(self, portfolio: PaperPortfolio) -> StrategyProfile:
        return self._strategies.resolve(portfolio.strategy_id)

    # ------------------------------------------------------------------ portfolios
    def list_portfolios(self) -> list[PaperPortfolio]:
        return list(self._store.list_portfolios())

    def get_portfolio(self, portfolio_id: str) -> PaperPortfolio:
        return self._require(portfolio_id)

    async def create_portfolio(
        self,
        *,
        name: str,
        starting_capital: Decimal,
        currency: str = "USD",
        strategy_id: str | None = None,
    ) -> PortfolioView:
        self._require_storage()
        title = " ".join(name.split())
        if not 1 <= len(title) <= 60:
            raise ValidationError("portfolio name must be 1-60 characters")
        capital = _money(starting_capital, "starting capital")
        code = currency.strip().upper()
        if len(code) != 3 or not code.isalpha():
            raise ValidationError("currency must be a three-letter code")
        if strategy_id is not None:
            self._strategies.get(strategy_id)
        now = self._clock()
        portfolio = PaperPortfolio(
            portfolio_id=f"P-{uuid.uuid4().hex[:10]}",
            name=title,
            base_currency=CurrencyCode(code),
            starting_capital=capital,
            created_at=now,
            strategy_id=strategy_id,
        )
        flow = CashFlow(
            f"F-{uuid.uuid4().hex[:12]}",
            CashFlowKind.CONTRIBUTION,
            capital,
            now,
            portfolio.base_currency,
        )
        with self._store.transaction():
            self._store.create_portfolio(portfolio, flow)
            self._store.record_valuation(
                portfolio.portfolio_id, ValuationPoint(now, capital, capital, capital, "created")
            )
            self._store.append_audit(
                at=now,
                actor="user",
                action="paper.portfolio.created",
                subject=portfolio.portfolio_id,
                detail={
                    "name": title,
                    "currency": code,
                    "starting_capital": str(capital),
                    "strategy_id": strategy_id,
                },
            )
        return await self.view(portfolio.portfolio_id, record=False)

    def set_strategy(self, portfolio_id: str, strategy_id: str | None) -> PaperPortfolio:
        self._require(portfolio_id)
        if strategy_id is not None:
            self._strategies.get(strategy_id)
        with self._store.transaction():
            self._store.set_portfolio_strategy(portfolio_id, strategy_id)
            self._store.append_audit(
                at=self._clock(),
                actor="user",
                action="paper.portfolio.strategy",
                subject=portfolio_id,
                detail={"strategy_id": strategy_id},
            )
        return self._require(portfolio_id)

    # ------------------------------------------------------------------ valuation
    @staticmethod
    def _last_fill_prices(ledger: Portfolio) -> dict[AssetId, Decimal]:
        prices: dict[AssetId, Decimal] = {}
        for trade in sorted(ledger.trades, key=lambda t: (t.occurred_at, t.trade_id)):
            prices[trade.asset] = trade.unit_price
        return prices

    async def _marks(self, assets: Sequence[AssetId]) -> tuple[dict[AssetId, QuoteView], list[str]]:
        warnings: list[str] = []
        if not assets:
            return {}, warnings
        try:
            views = await self._market.quotes(list(assets))
        except (MarketDataError, SlaifiError) as exc:
            warnings.append(
                f"Live prices are unavailable ({exc.message}); holdings are valued at their last fill price."
            )
            return {}, warnings
        except Exception as exc:  # noqa: BLE001 - never let a quote outage break the ledger view
            warnings.append(
                f"Live prices are unavailable ({type(exc).__name__}); holdings are valued at their last fill price."
            )
            return {}, warnings
        return {v.asset: v for v in views if v.quote is not None}, warnings

    def _valued(
        self,
        ledger: Portfolio,
        marks: dict[AssetId, QuoteView],
        now: datetime,
    ) -> tuple[PortfolioSnapshot, dict[AssetId, str]]:
        fills = self._last_fill_prices(ledger)
        prices: dict[AssetId, Decimal] = {}
        basis: dict[AssetId, str] = {}
        for position in build_positions(ledger.trades):
            if position.quantity <= 0:
                continue
            mark = marks.get(position.asset)
            if (
                mark is not None
                and mark.quote is not None
                and mark.quote.currency == ledger.base_currency
            ):
                prices[position.asset] = mark.quote.price
                basis[position.asset] = "last_known" if mark.quote.last_known else "quote"
            else:
                prices[position.asset] = fills[position.asset]
                basis[position.asset] = "last_fill"
        return value_portfolio(ledger, prices, as_of=now), basis

    async def view(self, portfolio_id: str, *, record: bool = True) -> PortfolioView:
        portfolio = self._require(portfolio_id)
        ledger = self._store.load_ledger(portfolio_id)
        held = [p.asset for p in build_positions(ledger.trades) if p.quantity > 0]
        marks, warnings = await self._marks(held)
        now = self._clock()
        snapshot, basis = self._valued(ledger, marks, now)
        stored_trades = self._store.list_trades(portfolio_id)
        classes = {p.asset: p.asset.asset_class.value for p in build_positions(ledger.trades)}
        positions = tuple(
            PositionView(
                valuation=v,
                price_basis=basis[v.position.asset],
                stale=basis[v.position.asset] != "quote",
                quote=marks.get(v.position.asset),
                asset_class=classes.get(v.position.asset, AssetClass.UNKNOWN.value),
            )
            for v in snapshot.positions
        )
        all_positions = build_positions(ledger.trades)
        realized = sum((p.realized_pnl for p in all_positions), _ZERO)
        unrealized = sum((v.unrealized_pnl for v in snapshot.positions), _ZERO)
        fees = sum((s.trade.fee for s in stored_trades), _ZERO)
        slippage = sum(
            (
                (s.execution.slippage_per_unit * s.trade.quantity) if s.execution else _ZERO
                for s in stored_trades
            ),
            _ZERO,
        )
        contributions = _ZERO
        for flow in ledger.cash_flows:
            if flow.kind is CashFlowKind.CONTRIBUTION:
                contributions += flow.amount
            elif flow.kind is CashFlowKind.WITHDRAWAL:
                contributions -= flow.amount
        total_pnl = snapshot.total_value - contributions
        complete = all(p.price_basis == "quote" for p in positions)
        if positions and not complete:
            warnings.append(
                "Some holdings are valued at their last fill price, not a current quotation."
            )
        for p in positions:
            if p.price_basis == "last_known":
                warnings.append(
                    f"{p.valuation.position.asset.symbol} is valued at its last known price "
                    "(live data sources could not be reached)."
                )
        if record:
            self._maybe_record_view(portfolio, snapshot, now)
        return PortfolioView(
            portfolio=portfolio,
            snapshot=snapshot,
            positions=positions,
            as_of=now,
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            fees_paid=fees,
            slippage_cost=slippage,
            net_contributions=contributions,
            total_pnl=total_pnl,
            simple_return=float(total_pnl / contributions) if contributions > 0 else None,
            valuation_complete=complete,
            strategy_id=portfolio.strategy_id,
            warnings=tuple(dict.fromkeys(warnings)),
        )

    def _maybe_record_view(
        self, portfolio: PaperPortfolio, snapshot: PortfolioSnapshot, now: datetime
    ) -> None:
        points = self._store.list_valuations(portfolio.portfolio_id, limit=1)
        if points:
            last = points[-1]
            age = (now - last.at).total_seconds()
            if age < VIEW_RECORD_INTERVAL_SECONDS or last.total_value == snapshot.total_value:
                return
        self._store.record_valuation(
            portfolio.portfolio_id,
            ValuationPoint(now, snapshot.total_value, _ZERO, snapshot.cash_balance, "view"),
        )

    # ------------------------------------------------------------------ cash movements
    async def deposit(
        self, portfolio_id: str, amount: Decimal, *, note: str | None = None
    ) -> PortfolioView:
        return await self._cash_flow(portfolio_id, amount, CashFlowKind.CONTRIBUTION, note)

    async def withdraw(
        self, portfolio_id: str, amount: Decimal, *, note: str | None = None
    ) -> PortfolioView:
        return await self._cash_flow(portfolio_id, amount, CashFlowKind.WITHDRAWAL, note)

    async def _cash_flow(
        self, portfolio_id: str, amount: Decimal, kind: CashFlowKind, note: str | None
    ) -> PortfolioView:
        self._require_storage()
        portfolio = self._require(portfolio_id)
        value = _money(amount, "amount")
        clean_note = " ".join(note.split())[:200] if note else None
        async with self._lock:
            current = await self.view(portfolio_id, record=False)
            now = self._clock()
            if kind is CashFlowKind.WITHDRAWAL:
                if value > current.snapshot.cash_balance:
                    raise ValidationError(
                        f"cannot withdraw {value}: only {current.snapshot.cash_balance:.2f} cash is available"
                    )
                strategy = self.strategy_for(portfolio)
                required = current.snapshot.total_value * Decimal(str(strategy.cash_reserve_rate))
                remaining = current.snapshot.cash_balance - value
                if strategy.cash_reserve_rate > 0 and remaining < required:
                    raise ConflictError(
                        f"Withdrawing {value} would leave {remaining:.2f} cash, below the strategy's "
                        f"{strategy.cash_reserve_rate:.0%} reserve ({required:.2f}). "
                        "Withdraw less or change the reserve first."
                    )
            flow = CashFlow(f"F-{uuid.uuid4().hex[:12]}", kind, value, now, portfolio.base_currency)
            signed = value if kind is CashFlowKind.CONTRIBUTION else -value
            with self._store.transaction():
                self._store.append_cash_flow(portfolio_id, flow, note=clean_note)
                self._store.record_valuation(
                    portfolio_id,
                    ValuationPoint(
                        now,
                        current.snapshot.total_value + signed,
                        signed,
                        current.snapshot.cash_balance + signed,
                        kind.value,
                    ),
                )
                self._store.append_audit(
                    at=now,
                    actor="user",
                    action=f"paper.cash.{kind.value}",
                    subject=portfolio_id,
                    detail={"flow_id": flow.flow_id, "amount": str(value), "note": clean_note},
                )
        return await self.view(portfolio_id, record=False)

    # ------------------------------------------------------------------ orders
    async def _volatility(self, asset: AssetId) -> float | None:
        try:
            history = await self._market.history(asset, days=400, interval="1day")
        except Exception:  # noqa: BLE001 - optional input to a soft check
            return None
        closes = [float(b.close) for b in history.bars]
        if len(closes) < 22:
            return None
        rets = [r for r in simple_returns(closes[-253:]) if r is not None]
        try:
            return historical_volatility(rets, periods_per_year=252)
        except Exception:  # noqa: BLE001
            return None

    def drawdown(self, portfolio_id: str) -> float | None:
        """Current drawdown of the time-weighted equity index (negative or zero), if measurable."""

        return self._drawdown(portfolio_id)

    def _drawdown(self, portfolio_id: str) -> float | None:
        points = [
            EquityPoint(p.at, p.total_value, p.net_flow)
            for p in self._store.list_valuations(portfolio_id)
        ]
        summary = summarize_performance(points)
        return summary.current_drawdown

    async def place_order(
        self,
        portfolio_id: str,
        *,
        symbol: str,
        side: TradeSide,
        quantity: Decimal | None = None,
        notional: Decimal | None = None,
        close_position: bool = False,
        client_order_id: str | None = None,
        exchange: str | None = None,
        asset_class: AssetClass | None = None,
        dry_run: bool = False,
        actor: str = "user",
    ) -> OrderOutcome:
        if not dry_run:
            self._require_storage()
        portfolio = self._require(portfolio_id)
        cid = client_order_id or f"O-{uuid.uuid4().hex[:16]}"
        if len(cid) > 80:
            raise ValidationError("client_order_id is too long")
        async with self._lock:
            existing = self._store.find_trade_by_client_order(portfolio_id, cid)
            if existing is not None and not dry_run:
                request = OrderRequest(
                    portfolio_id,
                    existing.trade.asset,
                    existing.trade.side,
                    cid,
                    quantity=existing.trade.quantity,
                )
                assert existing.execution is not None
                decision = OrderDecision(
                    OrderStatus.FILLED,
                    request,
                    trade=existing.trade,
                    execution=existing.execution,
                    warnings=("This order id was already executed; no new order was placed.",),
                )
                return OrderOutcome(
                    decision,
                    existing.trade.asset,
                    True,
                    False,
                    await self.view(portfolio_id, record=False),
                    portfolio.strategy_id,
                )

            asset = await self._canonical_asset(portfolio_id, symbol, exchange, asset_class)
            request = OrderRequest(
                portfolio_id=portfolio_id,
                asset=asset,
                side=side,
                client_order_id=cid,
                quantity=quantity,
                notional=notional,
                close_position=close_position,
            )
            quote_view, quote_problem = await self._quote_or_reason(asset)
            ledger0 = self._store.load_ledger(portfolio_id)
            held = [
                p.asset
                for p in build_positions(ledger0.trades)
                if p.quantity > 0 and p.asset != asset
            ]
            marks, _ = await self._marks(held)
            strategy = self.strategy_for(portfolio)
            volatility = (
                await self._volatility(asset)
                if side is TradeSide.BUY and strategy.max_annualized_volatility
                else None
            )
            now = self._clock()

            with self._store.transaction():
                ledger = self._store.load_ledger(portfolio_id)
                snapshot, _basis = self._valued(ledger, marks, now)
                if quote_view is None:
                    decision = OrderDecision(
                        OrderStatus.REJECTED,
                        request,
                        rejections=(
                            Rejection(
                                RejectionCode.QUOTE_UNAVAILABLE,
                                quote_problem
                                or "No current quotation is available for this asset.",
                            ),
                        ),
                    )
                else:
                    decision = evaluate_order(
                        request,
                        snapshot=snapshot,
                        quote=quote_view.quote,
                        policy=self._policy,
                        costs=strategy.costs,
                        now=now,
                        trade_id=f"T-{uuid.uuid4().hex[:16]}",
                        strategy=strategy,
                        portfolio_drawdown=self._drawdown(portfolio_id),
                        annualized_volatility=volatility,
                    )
                if dry_run:
                    return OrderOutcome(decision, asset, False, True, None, portfolio.strategy_id)
                if decision.status is OrderStatus.FILLED:
                    assert decision.trade is not None and decision.execution is not None
                    self._store.append_trade(portfolio_id, decision.trade, cid, decision.execution)
                    ledger_after = self._store.load_ledger(portfolio_id)
                    prices_marks = dict(marks)
                    if quote_view is not None:
                        prices_marks[asset] = quote_view
                    after, _ = self._valued(ledger_after, prices_marks, now)
                    self._store.record_valuation(
                        portfolio_id,
                        ValuationPoint(now, after.total_value, _ZERO, after.cash_balance, "trade"),
                    )
                    self._store.append_audit(
                        at=now,
                        actor=actor,
                        action="paper.order.filled",
                        subject=portfolio_id,
                        detail={
                            "trade_id": decision.trade.trade_id,
                            "client_order_id": cid,
                            "symbol": asset.display_symbol,
                            "side": side.value,
                            "quantity": str(decision.trade.quantity),
                            "execution_price": str(decision.execution.execution_price),
                            "quote_price": str(decision.execution.quote_price),
                            "commission": str(decision.execution.commission),
                            "data_mode": decision.execution.data_mode,
                            "strategy_id": strategy.strategy_id,
                        },
                    )
                else:
                    summary = "; ".join(r.message for r in decision.rejections)[:500]
                    self._store.record_rejection(
                        portfolio_id, cid, now, summary, decision.rejections
                    )
                    self._store.append_audit(
                        at=now,
                        actor=actor,
                        action="paper.order.rejected",
                        subject=portfolio_id,
                        detail={
                            "client_order_id": cid,
                            "symbol": asset.display_symbol,
                            "side": side.value,
                            "codes": [r.code.value for r in decision.rejections],
                        },
                    )
        view = await self.view(portfolio_id, record=False)
        return OrderOutcome(decision, asset, False, False, view, portfolio.strategy_id)

    async def _quote_or_reason(self, asset: AssetId) -> tuple[QuoteView | None, str | None]:
        try:
            view = await self._market.quote(asset)
        except SlaifiError as exc:
            return None, exc.message
        except Exception as exc:  # noqa: BLE001
            return None, f"The quotation service failed ({type(exc).__name__})."
        if view.quote is None:
            detail = " ".join(view.provenance.notes) or "No data source returned a quotation."
            return None, f"NOT AVAILABLE: {detail}"
        return view, None

    async def _canonical_asset(
        self, portfolio_id: str, symbol: str, exchange: str | None, asset_class: AssetClass | None
    ) -> AssetId:
        """Reuse the exact AssetId of an existing holding so the ledger never splits a position."""

        text = symbol.strip().upper()
        ledger = self._store.load_ledger(portfolio_id)
        for trade in ledger.trades:
            if trade.asset.symbol == text and (
                exchange is None or (trade.asset.exchange or "") == exchange.upper()
            ):
                return trade.asset
        return await self._market.resolve_asset(text, exchange=exchange, asset_class=asset_class)

    # ------------------------------------------------------------------ history & performance
    def history(self, portfolio_id: str, limit: int = 200) -> list[HistoryEntry]:
        self._require(portfolio_id)
        entries: list[HistoryEntry] = []
        for stored in self._store.list_trades(portfolio_id):
            t = stored.trade
            ex = stored.execution
            entries.append(
                HistoryEntry(
                    t.occurred_at,
                    "trade",
                    f"{t.side.value.upper()} {t.quantity} {t.asset.display_symbol} @ {t.unit_price:.4f}",
                    {
                        "trade_id": t.trade_id,
                        "symbol": t.asset.display_symbol,
                        "side": t.side.value,
                        "quantity": str(t.quantity),
                        "price": str(t.unit_price),
                        "fee": str(t.fee),
                        "gross": str(t.quantity * t.unit_price),
                        "quote_price": str(ex.quote_price) if ex else None,
                        "data_mode": ex.data_mode if ex else None,
                    },
                )
            )
        for stored_flow in self._store.list_cash_flows(portfolio_id):
            f = stored_flow.flow
            kind = (
                "initial"
                if stored_flow.origin in {"initial", "reset"}
                else ("deposit" if f.kind is CashFlowKind.CONTRIBUTION else "withdrawal")
            )
            label = {
                "initial": "Starting capital",
                "deposit": "Deposit",
                "withdrawal": "Withdrawal",
            }[kind]
            entries.append(
                HistoryEntry(
                    f.occurred_at,
                    kind,
                    f"{label} {f.amount:.2f} {f.currency}",
                    {"flow_id": f.flow_id, "amount": str(f.amount), "note": stored_flow.note},
                )
            )
        for rej in self._store.list_rejections(portfolio_id, limit=limit):
            entries.append(
                HistoryEntry(
                    rej.occurred_at,
                    "rejection",
                    f"Order rejected: {rej.summary}",
                    {
                        "client_order_id": rej.client_order_id,
                        "codes": [r.code.value for r in rej.rejections],
                    },
                )
            )
        for audit in self._store.list_audit(limit=500, subject=portfolio_id):
            if audit.action == "paper.portfolio.reset":
                entries.append(
                    HistoryEntry(audit.at, "reset", "Portfolio reset", dict(audit.detail))
                )
        entries.sort(key=lambda e: e.at, reverse=True)
        return entries[:limit]

    async def performance(self, portfolio_id: str) -> PerformanceView:
        view = await self.view(portfolio_id, record=True)
        points = [
            EquityPoint(p.at, p.total_value, p.net_flow)
            for p in self._store.list_valuations(portfolio_id)
        ]
        now_point = EquityPoint(view.as_of, view.snapshot.total_value, _ZERO)
        if not points or points[-1].at < now_point.at:
            points.append(now_point)
        summary = summarize_performance(points)
        total = view.snapshot.total_value
        weights = (
            [float(v.market_value / total) for v in view.snapshot.positions] if total > 0 else []
        )
        hhi = None
        invested = view.snapshot.securities_market_value
        if invested > 0:
            hhi = sum((float(v.market_value / invested)) ** 2 for v in view.snapshot.positions)
        notes = [
            summary.note,
            "Returns are in the portfolio's base currency; no FX conversion is applied.",
        ]
        return PerformanceView(
            portfolio_id=portfolio_id,
            summary=summary,
            equity_curve=tuple((p.at, p.total_value) for p in points),
            realized_pnl=view.realized_pnl,
            unrealized_pnl=view.unrealized_pnl,
            total_pnl=view.total_pnl,
            net_contributions=view.net_contributions,
            simple_return=view.simple_return,
            fees_paid=view.fees_paid,
            slippage_cost=view.slippage_cost,
            exposure=float(invested / total) if total > 0 else None,
            cash_weight=float(view.snapshot.cash_balance / total) if total > 0 else None,
            largest_position_weight=max(weights) if weights else None,
            concentration_hhi=hhi,
            notes=tuple(notes),
        )

    # ------------------------------------------------------------------ reset
    async def reset(
        self,
        portfolio_id: str,
        *,
        confirm: bool,
        starting_capital: Decimal | None = None,
    ) -> PortfolioView:
        self._require_storage()
        portfolio = self._require(portfolio_id)
        if confirm is not True:
            raise ValidationError(
                "Resetting erases this portfolio's positions and cash; pass confirm=true to proceed."
            )
        capital = (
            _money(starting_capital, "starting capital")
            if starting_capital is not None
            else portfolio.starting_capital
        )
        now = self._clock()
        async with self._lock:
            flow = CashFlow(
                f"F-{uuid.uuid4().hex[:12]}",
                CashFlowKind.CONTRIBUTION,
                capital,
                now,
                portfolio.base_currency,
            )
            with self._store.transaction():
                epoch = self._store.reset_portfolio(
                    portfolio_id, starting_capital=capital, initial_flow=flow, now=now
                )
                self._store.record_valuation(
                    portfolio_id, ValuationPoint(now, capital, capital, capital, "reset")
                )
                self._store.append_audit(
                    at=now,
                    actor="user",
                    action="paper.portfolio.reset",
                    subject=portfolio_id,
                    detail={
                        "new_epoch": epoch,
                        "starting_capital": str(capital),
                        "previous_starting_capital": str(portfolio.starting_capital),
                    },
                )
        return await self.view(portfolio_id, record=False)

    # ------------------------------------------------------------------ reconciliation
    def reconcile(self, portfolio_id: str | None = None) -> ReconciliationReport:
        now = self._clock()
        ids = (
            [portfolio_id]
            if portfolio_id
            else [p.portfolio_id for p in self._store.list_portfolios()]
        )
        issues: list[ReconciliationIssue] = []
        trade_count = flow_count = 0
        cash_total: Decimal | None = None
        for pid in ids:
            portfolio = self._require(pid)
            trades = self._store.list_trades(pid)
            flows = self._store.list_cash_flows(pid)
            trade_count += len(trades)
            flow_count += len(flows)
            events: list[tuple[datetime, int, Any]] = [(s.trade.occurred_at, 1, s) for s in trades]
            events += [(s.flow.occurred_at, 0, s) for s in flows]
            events.sort(key=lambda e: (e[0], e[1]))
            cash = _ZERO
            held: dict[AssetId, Decimal] = {}
            for _, kind, item in events:
                if kind == 0:
                    f = item.flow
                    if f.currency != portfolio.base_currency:
                        issues.append(
                            ReconciliationIssue(
                                "error",
                                "currency",
                                f"cash flow {f.flow_id} is not in {portfolio.base_currency}",
                            )
                        )
                    cash += (
                        f.amount
                        if f.kind in (CashFlowKind.CONTRIBUTION, CashFlowKind.DIVIDEND)
                        else -f.amount
                    )
                else:
                    t = item.trade
                    if t.currency != portfolio.base_currency:
                        issues.append(
                            ReconciliationIssue(
                                "error",
                                "currency",
                                f"trade {t.trade_id} is not in {portfolio.base_currency}",
                            )
                        )
                    gross = t.quantity * t.unit_price
                    if t.side is TradeSide.BUY:
                        cash -= gross + t.fee
                        held[t.asset] = held.get(t.asset, _ZERO) + t.quantity
                    else:
                        cash += gross - t.fee
                        held[t.asset] = held.get(t.asset, _ZERO) - t.quantity
                        if held[t.asset] < 0:
                            issues.append(
                                ReconciliationIssue(
                                    "error",
                                    "negative_position",
                                    f"{t.asset.display_symbol} went negative at trade {t.trade_id}",
                                )
                            )
                if cash < Decimal("-0.005"):
                    issues.append(
                        ReconciliationIssue(
                            "error",
                            "negative_cash",
                            f"cash went negative ({cash:.2f}) in {portfolio.name}",
                        )
                    )
            cash_total = (cash_total or _ZERO) + cash
            audited = {
                a.detail.get("trade_id")
                for a in self._store.list_audit(limit=100000, subject=pid)
                if a.action == "paper.order.filled"
            }
            for s in trades:
                if s.trade.trade_id not in audited:
                    issues.append(
                        ReconciliationIssue(
                            "warning",
                            "missing_audit",
                            f"trade {s.trade.trade_id} has no audit entry",
                        )
                    )
            points = self._store.list_valuations(pid, limit=1)
            if (
                points
                and events
                and points[-1].at >= events[-1][0]
                and abs(points[-1].cash - cash) > Decimal("0.01")
                and points[-1].source != "view"
            ):
                issues.append(
                    ReconciliationIssue(
                        "error",
                        "valuation_cash_mismatch",
                        f"last recorded cash {points[-1].cash:.2f} differs from the ledger ({cash:.2f})",
                    )
                )
        intact, problem = self._store.verify_audit_chain()
        if not intact and problem:
            issues.append(ReconciliationIssue("error", "audit_chain", problem))
        return ReconciliationReport(
            portfolio_id=portfolio_id,
            checked_at=now,
            trade_count=trade_count,
            cash_flow_count=flow_count,
            cash_balance=cash_total,
            issues=tuple(issues),
            database_integrity=self._store.integrity(),
            audit_chain_intact=intact,
        )
