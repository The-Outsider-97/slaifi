"""Deterministic simulated order execution. Nothing here can place a real-money order.

The provider quotation and the simulated fill are kept apart: the fill price includes slippage
and the trade carries a commission (the strategy's proportional assumption plus the platform's flat
fee per trade).
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
from slaifi.domain.portfolio import SHORT_MARGIN_RATE, PortfolioSnapshot, Trade, TradeSide
from slaifi.domain.strategies import StrategyProfile, TransactionCosts
from slaifi.engines.strategy import check_buy, check_short

_PRICE_STEP = Decimal("0.000001")
_CENT = Decimal("0.01")
_ZERO = Decimal("0")


def commission_for(gross: Decimal, costs: TransactionCosts, flat_fee: Decimal = _ZERO) -> Decimal:
    """Proportional commission (with its minimum) plus the platform's flat fee per trade."""

    fee = max(gross * costs.commission_rate, costs.commission_minimum) + flat_fee
    return fee.quantize(_CENT, rounding=ROUND_HALF_UP)


def execution_price(quote_price: Decimal, side: TradeSide, costs: TransactionCosts) -> Decimal:
    """Slippage moves the fill against the trader: buys and covers pay more; sells and shorts receive less."""

    pays_more = side in (TradeSide.BUY, TradeSide.COVER)
    factor = Decimal(1) + costs.slippage_rate if pays_more else Decimal(1) - costs.slippage_rate
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
    flat_fee: Decimal = _ZERO,
    whole_mix_verified: bool = False,
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

    side = request.side
    if request.close_position:
        quantity = held if side is TradeSide.SELL else -held
        if (side is TradeSide.SELL and held < 0) or (side is TradeSide.COVER and held > 0):
            quantity = _ZERO
    elif request.quantity is not None:
        quantity = request.quantity.quantize(quantum, rounding=ROUND_DOWN)
    else:
        assert request.notional is not None
        quantity = (request.notional / fill_price).quantize(quantum, rounding=ROUND_DOWN)

    if quantity <= 0:
        message = (
            "There is no open position to close."
            if request.close_position
            else "The order is too small to trade any quantity at this price."
        )
        code = (
            RejectionCode.INSUFFICIENT_POSITION
            if request.close_position
            else RejectionCode.QUANTITY_TOO_SMALL
        )
        return _reject(request, Rejection(code, message))

    gross = (quantity * fill_price).quantize(_CENT, rounding=ROUND_HALF_UP)
    fee = commission_for(gross, costs, flat_fee)
    rejections: list[Rejection] = []
    name = request.asset.display_symbol
    if side is TradeSide.BUY:
        if held < 0:
            rejections.append(
                Rejection(
                    RejectionCode.WRONG_DIRECTION,
                    f"{name} is a short position; use Cover to buy it back.",
                )
            )
        needed = gross + fee
        if needed > snapshot.free_cash:
            locked = snapshot.margin_required
            suffix = f" ({locked:.2f} is held as collateral for shorts)" if locked > 0 else ""
            rejections.append(
                Rejection(
                    RejectionCode.INSUFFICIENT_CASH,
                    f"The order needs {needed:.2f} but only {snapshot.free_cash:.2f} cash is "
                    f"available{suffix}.",
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
                if finding.severity == "hard" and not (
                    whole_mix_verified and finding.code == "concentration_hhi"
                ):
                    rejections.append(Rejection(RejectionCode.STRATEGY_CONSTRAINT, finding.message))
                elif finding.severity == "hard":
                    # One step of a complete rebalance: the finished mix was checked against this
                    # same limit, and an order-by-order view would block any large rebalance.
                    warnings.append(finding.message + " (the finished mix was checked as a whole)")
                else:
                    warnings.append(finding.message)
    elif side is TradeSide.SELL:
        if held < 0:
            rejections.append(
                Rejection(
                    RejectionCode.WRONG_DIRECTION,
                    f"{name} is a short position; use Cover to buy it back.",
                )
            )
        elif quantity > held:
            rejections.append(
                Rejection(
                    RejectionCode.INSUFFICIENT_POSITION,
                    f"The order sells {quantity} but only {held} is held. To bet on a price fall "
                    "use Short instead.",
                )
            )
        if snapshot.cash_balance + gross - fee < 0:
            rejections.append(
                Rejection(
                    RejectionCode.INSUFFICIENT_CASH,
                    f"The sale brings in {gross:.2f} but costs {fee:.2f} in fees, and only "
                    f"{snapshot.cash_balance:.2f} cash is available to cover the difference.",
                )
            )
    elif side is TradeSide.SHORT:
        if held > 0:
            rejections.append(
                Rejection(
                    RejectionCode.WRONG_DIRECTION,
                    f"{name} is held long; sell it first (a position cannot be long and short).",
                )
            )
        if strategy is None:
            rejections.append(
                Rejection(
                    RejectionCode.SHORT_NOT_ALLOWED,
                    "Short selling needs an active strategy that sets a short exposure limit.",
                )
            )
        else:
            for finding in check_short(
                snapshot,
                request.asset,
                trade_value=gross,
                fee=fee,
                strategy=strategy,
                annualized_volatility=annualized_volatility,
                portfolio_drawdown=portfolio_drawdown,
            ):
                if finding.severity == "hard":
                    code = (
                        RejectionCode.SHORT_NOT_ALLOWED
                        if finding.code == "short_not_allowed"
                        else RejectionCode.STRATEGY_CONSTRAINT
                    )
                    rejections.append(Rejection(code, finding.message))
                else:
                    warnings.append(finding.message)
        # Collateral: proceeds stay locked and a further half of the short's value is required.
        cash_after = snapshot.cash_balance + gross - fee
        required = (snapshot.short_value + gross) * SHORT_MARGIN_RATE
        if cash_after < required:
            rejections.append(
                Rejection(
                    RejectionCode.INSUFFICIENT_MARGIN,
                    f"Collateral for the shorts would need {required:.2f} in cash (150 % of their "
                    f"value) but only {cash_after:.2f} would be available.",
                )
            )
        warnings.append(
            "Simulated short sale: borrow fees, dividends owed and share recalls are not modelled. "
            "A short can lose more than the amount received."
        )
    else:  # COVER
        owed = -held if held < 0 else _ZERO
        if held >= 0:
            rejections.append(
                Rejection(
                    RejectionCode.INSUFFICIENT_POSITION,
                    f"There is no short position in {name} to cover.",
                )
            )
        elif quantity > owed:
            rejections.append(
                Rejection(
                    RejectionCode.INSUFFICIENT_POSITION,
                    f"The order covers {quantity} but only {owed} is short.",
                )
            )
        if gross + fee > snapshot.cash_balance:
            rejections.append(
                Rejection(
                    RejectionCode.INSUFFICIENT_CASH,
                    f"Covering needs {gross + fee:.2f} but only {snapshot.cash_balance:.2f} "
                    "cash is available.",
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
    net = gross - fee if request.side.opens_or_adds_cash else -(gross + fee)
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
