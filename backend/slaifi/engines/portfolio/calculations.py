"""Deterministic portfolio accounting and valuation calculations."""
from collections import defaultdict
from collections.abc import Mapping,Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from slaifi.core.exceptions import FinancialCalculationError,ValidationError
from slaifi.core.types import CurrencyCode
from slaifi.domain.assets import AssetId
from slaifi.domain.portfolio import CashFlow,CashFlowKind,Portfolio,PortfolioSnapshot,Position,PositionValuation,Trade,TradeSide

@dataclass(slots=True)
class _PositionState:
    quantity: Decimal=Decimal("0")
    cost_basis: Decimal=Decimal("0")
    realized_pnl: Decimal=Decimal("0")
    currency: CurrencyCode|None=None

def build_positions(trades: Sequence[Trade])->tuple[Position,...]:
    states:dict[AssetId,_PositionState]=defaultdict(_PositionState); seen:set[str]=set()
    for trade in sorted(trades,key=lambda item:(item.occurred_at,item.trade_id)):
        if trade.trade_id in seen: raise ValidationError(f"duplicate trade_id: {trade.trade_id}")
        seen.add(trade.trade_id); state=states[trade.asset]
        if state.currency is None: state.currency=trade.currency
        elif state.currency!=trade.currency: raise FinancialCalculationError("mixed trade currencies require an explicit FX conversion layer")
        if trade.side is TradeSide.BUY:
            state.cost_basis += trade.quantity*trade.unit_price+trade.fee; state.quantity += trade.quantity; continue
        if trade.quantity>state.quantity: raise FinancialCalculationError(f"sell quantity exceeds long position for {trade.asset.display_symbol}")
        average=state.cost_basis/state.quantity; proceeds=trade.quantity*trade.unit_price-trade.fee
        state.realized_pnl += proceeds-average*trade.quantity; state.quantity -= trade.quantity; state.cost_basis -= average*trade.quantity
        if state.quantity==0: state.cost_basis=Decimal("0")
    output=[]
    for asset,state in sorted(states.items(),key=lambda item:item[0].display_symbol):
        if state.currency is None: continue
        average=state.cost_basis/state.quantity if state.quantity>0 else Decimal("0")
        output.append(Position(asset,state.quantity,average,state.realized_pnl,state.currency))
    return tuple(output)

def cash_balance(portfolio: Portfolio,*,initial_cash:Decimal=Decimal("0"))->Decimal:
    balance=initial_cash
    for trade in portfolio.trades:
        _require_currency(trade.currency,portfolio.base_currency); gross=trade.quantity*trade.unit_price
        balance += gross-trade.fee if trade.side is TradeSide.SELL else -(gross+trade.fee)
    for flow in portfolio.cash_flows:
        _require_currency(flow.currency,portfolio.base_currency)
        balance += flow.amount if flow.kind in (CashFlowKind.CONTRIBUTION,CashFlowKind.DIVIDEND) else -flow.amount
    return balance

def aggregate_income_by_currency(cash_flows: Sequence[CashFlow])->dict[CurrencyCode,Decimal]:
    totals:dict[CurrencyCode,Decimal]=defaultdict(lambda:Decimal("0"))
    for flow in cash_flows:
        if flow.kind is CashFlowKind.DIVIDEND: totals[flow.currency]+=flow.amount
    return dict(totals)

def portfolio_weights(positions:Sequence[Position],prices:Mapping[AssetId,Decimal])->dict[AssetId,float]:
    values={position.asset:position.quantity*_validated_price(position.asset,prices) for position in positions if position.quantity>0}
    total=sum(values.values(),Decimal("0"))
    return {} if total==0 else {asset:float(value/total) for asset,value in values.items()}

def value_portfolio(portfolio:Portfolio,prices:Mapping[AssetId,Decimal],*,as_of:datetime,initial_cash:Decimal=Decimal("0"))->PortfolioSnapshot:
    if as_of.tzinfo is None or as_of.utcoffset() is None: raise ValidationError("as_of must be timezone-aware")
    positions=build_positions(portfolio.trades); balance=cash_balance(portfolio,initial_cash=initial_cash)
    raw={position.asset:position.quantity*_validated_price(position.asset,prices) for position in positions if position.quantity>0}; securities=sum(raw.values(),Decimal("0")); total=balance+securities
    valuations=[]
    for position in positions:
        if position.quantity==0: continue
        price=_validated_price(position.asset,prices); market=raw[position.asset]; weight=float(market/total) if total>0 else None
        valuations.append(PositionValuation(position,price,market,(price-position.average_cost)*position.quantity,weight))
    return PortfolioSnapshot(portfolio.portfolio_id,as_of,portfolio.base_currency,balance,tuple(valuations),securities,total)

def _validated_price(asset:AssetId,prices:Mapping[AssetId,Decimal])->Decimal:
    try: price=prices[asset]
    except KeyError as exc: raise FinancialCalculationError(f"missing price for {asset.display_symbol}") from exc
    if price<=0: raise ValidationError(f"price for {asset.display_symbol} must be positive")
    return price

def _require_currency(actual:CurrencyCode,expected:CurrencyCode)->None:
    if actual!=expected: raise FinancialCalculationError(f"currency {actual} cannot be combined with base currency {expected} without FX")
