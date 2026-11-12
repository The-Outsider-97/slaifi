"""Deterministic simulated order execution. Nothing here can place a real-money order.

The provider quotation and the simulated fill are kept apart: the fill price includes slippage
and the trade carries a commission, both taken from the strategy's configured cost assumptions.
Stale, last-known, closed-market or unavailable quotes are refused according to the policy.
"""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from slaifi.domain.market import PriceQuote
from slaifi.domain.paper import (
    ExecutionDetails,
    ExecutionPolicy,
    OrderDecision,
    OrderRequest,
    OrderStatus,
    Rejection,
    RejectionCode,
)
from slaifi.domain.portfolio import PortfolioSnapshot, Trade, TradeSide
from slaifi.domain.strategies import StrategyProfile, TransactionCosts
from slaifi.engines.strategy import check_buy

_PRICE_STEP = Decimal("0.000001")
_CENT = Decimal("0.01")
_ZERO = Decimal("0")


def commission_for(gross: Decimal, costs: TransactionCosts) -> Decimal:
    fee = max(gross * costs.commission_rate, costs.commission_minimum)
    return fee.quantize(_CENT, rounding=ROUND_HALF_UP)


def execution_price(quote_price: Decimal, side: TradeSide, costs: TransactionCosts) -> Decimal:
    """Slippage moves the fill against the trader: buys pay more, sells receive less."""

    factor = (
        Decimal(1) + costs.slippage_rate
        if side is TradeSide.BUY
        else Decimal(1) - costs.slippage_rate
    )
    rounding = ROUND_HALF_UP
    return (quote_price * factor).quantize(_PRICE_STEP, rounding=rounding)


def _reject(request: OrderRequest, *rejections: Rejection) -> OrderDecision:
    return OrderDecision(OrderStatus.REJECTED, request, rejections=tuple(rejections))


def evaluate_order(
    request: OrderRequest,
    *,
    snapshot: PortfolioSnapshot,
    quote: PriceQuote | None,
    policy: ExecutionPolicy,
    costs: TransactionCosts,
    now: datetime,
    trade_id: str,
    strategy: StrategyProfile | None = None,
    portfolio_drawdown: float | None = None,
    annualized_volatility: float | None = None,
) -> OrderDecision:
    """Return a FILLED decision (with trade + audit details) or a REJECTED one with reasons."""

    if quote is None:
        return _reject(
            request,
            Rejection(
                RejectionCode.QUOTE_UNAVAILABLE, "No current quotation is available for this asset."
            ),
        )
    if quote.currency != snapshot.base_currency:
        return _reject(
            request,
            Rejection(
                RejectionCode.CURRENCY_MISMATCH,
                f"The instrument trades in {quote.currency} but the portfolio is in "
                f"{snapshot.base_currency}; no FX conversion is performed.",
            ),
        )

    warnings: list[str] = []
    notes: list[str] = []
    if quote.last_known:
        return _reject(
            request,
            Rejection(
                RejectionCode.QUOTE_LAST_KNOWN,
                "Only a last-known price is available because no live data source could be "
                "reached; simulated orders need a current quotation.",
            ),
        )
    if quote.is_market_open is False:
        if not policy.allow_closed_market:
            return _reject(
                request,
                Rejection(
                    RejectionCode.MARKET_CLOSED,
                    "The market is closed; simulated orders execute only while it is open.",
                ),
            )
        warnings.append("The market was closed; filled at the last observed price.")
    else:
        age = (now - quote.observed_at).total_seconds()
        if age > policy.max_quote_age_seconds:
            return _reject(
                request,
                Rejection(
                    RejectionCode.QUOTE_STALE,
                    f"The quotation is {int(age)} s old (limit {policy.max_quote_age_seconds} s).",
                ),
            )
    if quote.delayed:
        warnings.append("The quotation is delayed; the fill uses the delayed price.")
    if quote.is_market_open is None:
        notes.append("Market status was not reported by the data source.")

    fill_price = execution_price(quote.price, request.side, costs)
    held = _ZERO
    for valuation in snapshot.positions:
        if valuation.position.asset == request.asset:
            held = valuation.position.quantity
    quantum = Decimal(1).scaleb(-policy.quantity_decimals)

    if request.close_position:
        quantity = held
    elif request.quantity is not None:
        quantity = request.quantity.quantize(quantum, rounding=ROUND_DOWN)
    else:
        assert request.notional is not None
        quantity = (request.notional / fill_price).quantize(quantum, rounding=ROUND_DOWN)

    if quantity <= 0:
        message = (
            "There is no open position to close."
            if request.close_position
            else "The order is too small to buy or sell any quantity at this price."
        )
        code = (
            RejectionCode.INSUFFICIENT_POSITION
            if request.close_position
            else RejectionCode.QUANTITY_TOO_SMALL
        )
        return _reject(request, Rejection(code, message))

    gross = (quantity * fill_price).quantize(_CENT, rounding=ROUND_HALF_UP)
    fee = commission_for(gross, costs)
    rejections: list[Rejection] = []
    if request.side is TradeSide.BUY:
        needed = gross + fee
        if needed > snapshot.cash_balance:
            rejections.append(
                Rejection(
                    RejectionCode.INSUFFICIENT_CASH,
                    f"The order needs {needed:.2f} but only {snapshot.cash_balance:.2f} cash is available.",
                )
            )
        if strategy is not None:
            for finding in check_buy(
                snapshot,
                request.asset,
                trade_value=gross,
                fee=fee,
                strategy=strategy,
                annualized_volatility=annualized_volatility,
                portfolio_drawdown=portfolio_drawdown,
            ):
                if finding.severity == "hard":
                    rejections.append(Rejection(RejectionCode.STRATEGY_CONSTRAINT, finding.message))
                else:
                    warnings.append(finding.message)
    elif quantity > held:
        rejections.append(
            Rejection(
                RejectionCode.INSUFFICIENT_POSITION,
                f"The order sells {quantity} but only {held} is held; short selling is not supported.",
            )
        )
    if rejections:
        return _reject(request, *rejections)

    trade = Trade(
        trade_id=trade_id,
        asset=request.asset,
        side=request.side,
        quantity=quantity,
        unit_price=fill_price,
        fee=fee,
        occurred_at=now,
        currency=snapshot.base_currency,
    )
    net = -(gross + fee) if request.side is TradeSide.BUY else gross - fee
    details = ExecutionDetails(
        quote_price=quote.price,
        execution_price=fill_price,
        slippage_per_unit=abs(fill_price - quote.price),
        commission=fee,
        gross_amount=gross,
        net_cash_effect=net,
        currency=snapshot.base_currency,
        quote_observed_at=quote.observed_at,
        quote_source=quote.source,
        data_mode=(
            "delayed"
            if quote.delayed is True
            else "live"
            if quote.delayed is False
            else "live_delay_unknown"
        ),
        executed_at=now,
        market_open=quote.is_market_open,
        notes=tuple(notes),
    )
    return OrderDecision(
        OrderStatus.FILLED, request, trade=trade, execution=details, warnings=tuple(warnings)
    )
