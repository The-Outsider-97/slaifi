"""Deterministic portfolio accounting and valuation calculations."""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from slaifi.core.exceptions import FinancialCalculationError, ValidationError
from slaifi.core.types import CurrencyCode
from slaifi.domain.assets import AssetId
from slaifi.domain.portfolio import (
    CashFlow,
    CashFlowKind,
    Portfolio,
    PortfolioSnapshot,
    Position,
    PositionValuation,
    Trade,
    TradeSide,
)


@dataclass(slots=True)
class _PositionState:
    quantity: Decimal = Decimal("0")
    cost_basis: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    currency: CurrencyCode | None = None


def build_positions(trades: Sequence[Trade]) -> tuple[Position, ...]:
    """Aggregate trades using explicit weighted-average cost accounting."""

    states: dict[AssetId, _PositionState] = defaultdict(_PositionState)
    ordered = sorted(trades, key=lambda trade: (trade.occurred_at, trade.trade_id))
    seen_ids: set[str] = set()

    for trade in ordered:
        if trade.trade_id in seen_ids:
            raise ValidationError(f"duplicate trade_id: {trade.trade_id}")
        seen_ids.add(trade.trade_id)
        state = states[trade.asset]
        if state.currency is None:
            state.currency = trade.currency
        elif state.currency != trade.currency:
            raise FinancialCalculationError(
                "mixed trade currencies require an explicit FX conversion layer"
            )

        if trade.side is TradeSide.BUY:
            state.cost_basis += trade.quantity * trade.unit_price + trade.fee
            state.quantity += trade.quantity
            continue

        if trade.quantity > state.quantity:
            raise FinancialCalculationError(
                f"sell quantity exceeds long position for {trade.asset.display_symbol}"
            )
        if state.quantity <= 0:
            raise FinancialCalculationError("cannot sell from an empty position")

        average_cost = state.cost_basis / state.quantity
        proceeds = trade.quantity * trade.unit_price - trade.fee
        state.realized_pnl += proceeds - average_cost * trade.quantity
        state.quantity -= trade.quantity
        state.cost_basis -= average_cost * trade.quantity
        if state.quantity == 0:
            state.cost_basis = Decimal("0")

    positions: list[Position] = []
    for asset, state in sorted(
        states.items(),
        key=lambda item: item[0].display_symbol,
    ):
        if state.currency is None:
            continue
        average_cost = (
            state.cost_basis / state.quantity
            if state.quantity > 0
            else Decimal("0")
        )
        positions.append(
            Position(
                asset=asset,
                quantity=state.quantity,
                average_cost=average_cost,
                realized_pnl=state.realized_pnl,
                currency=state.currency,
            )
        )
    return tuple(positions)


def cash_balance(
    portfolio: Portfolio,
    *,
    initial_cash: Decimal = Decimal("0"),
) -> Decimal:
    """Calculate base-currency cash without hidden FX conversion."""

    balance = initial_cash
    for trade in portfolio.trades:
        _require_currency(trade.currency, portfolio.base_currency)
        gross = trade.quantity * trade.unit_price
        if trade.side is TradeSide.BUY:
            balance -= gross + trade.fee
        else:
            balance += gross - trade.fee

    for flow in portfolio.cash_flows:
        _require_currency(flow.currency, portfolio.base_currency)
        if flow.kind in (CashFlowKind.CONTRIBUTION, CashFlowKind.DIVIDEND):
            balance += flow.amount
        elif flow.kind in (CashFlowKind.WITHDRAWAL, CashFlowKind.FEE):
            balance -= flow.amount
    return balance


def aggregate_income_by_currency(
    cash_flows: Sequence[CashFlow],
) -> dict[CurrencyCode, Decimal]:
    """Aggregate dividend income without performing FX conversion."""

    totals: dict[CurrencyCode, Decimal] = defaultdict(lambda: Decimal("0"))
    for flow in cash_flows:
        if flow.kind is CashFlowKind.DIVIDEND:
            totals[flow.currency] += flow.amount
    return dict(totals)


def portfolio_weights(
    positions: Sequence[Position],
    prices: Mapping[AssetId, Decimal],
) -> dict[AssetId, float]:
    """Return invested-asset weights; closed positions are excluded."""

    values: dict[AssetId, Decimal] = {}
    for position in positions:
        if position.quantity == 0:
            continue
        price = _validated_price(position.asset, prices)
        values[position.asset] = position.quantity * price
    total = sum(values.values(), Decimal("0"))
    if total == 0:
        return {}
    return {asset: float(value / total) for asset, value in values.items()}


def value_portfolio(
    portfolio: Portfolio,
    prices: Mapping[AssetId, Decimal],
    *,
    as_of: datetime,
    initial_cash: Decimal = Decimal("0"),
) -> PortfolioSnapshot:
    """Calculate market value, unrealized P/L, allocation, and cash at as_of."""

    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValidationError("as_of must be timezone-aware")
    positions = build_positions(portfolio.trades)
    balance = cash_balance(portfolio, initial_cash=initial_cash)

    raw_values: dict[AssetId, Decimal] = {}
    for position in positions:
        if position.quantity == 0:
            continue
        price = _validated_price(position.asset, prices)
        raw_values[position.asset] = position.quantity * price
    securities_value = sum(raw_values.values(), Decimal("0"))
    total_value = balance + securities_value

    valuations: list[PositionValuation] = []
    for position in positions:
        if position.quantity == 0:
            continue
        price = _validated_price(position.asset, prices)
        market_value = raw_values[position.asset]
        weight = float(market_value / total_value) if total_value > 0 else None
        valuations.append(
            PositionValuation(
                position=position,
                market_price=price,
                market_value=market_value,
                unrealized_pnl=(price - position.average_cost) * position.quantity,
                portfolio_weight=weight,
            )
        )

    return PortfolioSnapshot(
        portfolio_id=portfolio.portfolio_id,
        as_of=as_of,
        base_currency=portfolio.base_currency,
        cash_balance=balance,
        positions=tuple(valuations),
        securities_market_value=securities_value,
        total_value=total_value,
    )


def _validated_price(
    asset: AssetId,
    prices: Mapping[AssetId, Decimal],
) -> Decimal:
    try:
        price = prices[asset]
    except KeyError as exc:
        raise FinancialCalculationError(
            f"missing price for {asset.display_symbol}"
        ) from exc
    if price <= 0:
        raise ValidationError(
            f"price for {asset.display_symbol} must be positive"
        )
    return price


def _require_currency(actual: CurrencyCode, expected: CurrencyCode) -> None:
    if actual != expected:
        raise FinancialCalculationError(
            f"currency {actual} cannot be combined with base currency {expected} without FX"
        )
