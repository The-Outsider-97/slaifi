"""Pure order-execution rules: pricing, costs, and every reason an order must be refused."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from slaifi.core.types import CurrencyCode
from slaifi.domain.assets import AssetClass, AssetId
from slaifi.domain.market import PriceQuote
from slaifi.domain.paper import ExecutionPolicy, OrderRequest, OrderStatus, RejectionCode
from slaifi.domain.portfolio import PortfolioSnapshot, TradeSide
from slaifi.domain.strategies import DEFAULT_PRESET_ID, TransactionCosts, instantiate_preset
from slaifi.engines.paper import commission_for, evaluate_order

NOW = datetime(2026, 5, 1, 15, 0, tzinfo=UTC)
USD = CurrencyCode("USD")
ASSET = AssetId("KO", AssetClass.EQUITY, "NYSE", USD)
COSTS = TransactionCosts(
    commission_rate=Decimal("0.001"),
    commission_minimum=Decimal("1"),
    slippage_rate=Decimal("0.0005"),
)


def snapshot(cash: str = "10000") -> PortfolioSnapshot:
    return PortfolioSnapshot("p", NOW, USD, Decimal(cash), (), Decimal("0"), Decimal(cash))


def quote(**kw: object) -> PriceQuote:
    base = dict(
        asset=ASSET,
        price=Decimal("60.00"),
        currency=USD,
        observed_at=NOW - timedelta(seconds=30),
        source="test",
        is_market_open=True,
        delayed=False,
    )
    base.update(kw)
    return PriceQuote(**base)  # type: ignore[arg-type]


def order(**kw: object) -> OrderRequest:
    args = dict(
        portfolio_id="p",
        asset=ASSET,
        side=TradeSide.BUY,
        client_order_id="c1",
        quantity=Decimal("10"),
    )
    args.update(kw)
    return OrderRequest(**args)  # type: ignore[arg-type]


def run(
    req: OrderRequest,
    q: PriceQuote | None,
    policy: ExecutionPolicy | None = None,
    snap: PortfolioSnapshot | None = None,
):
    return evaluate_order(
        req,
        snapshot=snap or snapshot(),
        quote=q,
        policy=policy or ExecutionPolicy(),
        costs=COSTS,
        now=NOW,
        trade_id="t1",
        strategy=instantiate_preset(DEFAULT_PRESET_ID, strategy_id="s", name="s"),
        annualized_volatility=0.12,
    )


def codes(decision) -> set[RejectionCode]:
    return {r.code for r in decision.rejections}


def test_fill_uses_exact_decimal_arithmetic_with_slippage_and_commission() -> None:
    d = run(order(), quote())
    assert d.status is OrderStatus.FILLED
    ex = d.execution
    assert ex is not None
    assert ex.execution_price == Decimal("60.00") * (Decimal("1") + Decimal("0.0005"))
    assert ex.gross_amount == ex.execution_price * Decimal("10")
    assert ex.commission == commission_for(ex.gross_amount, COSTS)
    assert ex.commission >= Decimal("1")
    assert ex.net_cash_effect == -(ex.gross_amount + ex.commission)


def test_missing_quote_is_rejected_not_guessed() -> None:
    assert codes(run(order(), None)) == {RejectionCode.QUOTE_UNAVAILABLE}


def test_stale_quote_is_rejected() -> None:
    stale = quote(observed_at=NOW - timedelta(hours=3))
    assert RejectionCode.QUOTE_STALE in codes(run(order(), stale))


def test_closed_market_rejected_unless_policy_allows() -> None:
    closed = quote(is_market_open=False)
    assert run(order(), closed).status is OrderStatus.REJECTED
    assert (
        run(order(), closed, ExecutionPolicy(allow_closed_market=True)).status is OrderStatus.FILLED
    )


def test_last_known_quote_is_never_executable() -> None:
    d = run(order(), quote(last_known=True))
    assert d.status is OrderStatus.REJECTED
    assert d.trade is None
    assert codes(d) == {RejectionCode.QUOTE_LAST_KNOWN}


def test_insufficient_cash_is_rejected() -> None:
    d = run(order(quantity=Decimal("1000")), quote(), snap=snapshot("500"))
    assert d.status is OrderStatus.REJECTED
    assert d.trade is None


def test_selling_more_than_held_is_rejected() -> None:
    d = run(order(side=TradeSide.SELL, quantity=Decimal("5")), quote())
    assert d.status is OrderStatus.REJECTED


def test_currency_mismatch_is_rejected_without_conversion() -> None:
    eur = quote(currency=CurrencyCode("EUR"))
    assert RejectionCode.CURRENCY_MISMATCH in codes(run(order(), eur))
