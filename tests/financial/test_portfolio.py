from datetime import UTC, datetime
from decimal import Decimal

import pytest

from slaifi.core.types import CurrencyCode
from slaifi.domain.assets import AssetClass, AssetId
from slaifi.domain.portfolio import CashFlow, CashFlowKind, Portfolio, Trade, TradeSide
from slaifi.engines.portfolio import (
    aggregate_income_by_currency,
    build_positions,
    cash_balance,
    portfolio_weights,
    value_portfolio,
)
from slaifi.engines.utils.errors import FinancialCalculationError

USD = CurrencyCode("USD")
ASSET = AssetId("ABC", AssetClass.EQUITY, exchange="NYSE", currency=USD)


def trade(
    identifier: str,
    side: TradeSide,
    quantity: str,
    price: str,
    fee: str = "0",
) -> Trade:
    return Trade(
        trade_id=identifier,
        asset=ASSET,
        side=side,
        quantity=Decimal(quantity),
        unit_price=Decimal(price),
        fee=Decimal(fee),
        occurred_at=datetime(2026, 1, int(identifier[-1]), tzinfo=UTC),
        currency=USD,
    )


def test_weighted_average_cost_and_realized_pnl_reference() -> None:
    positions = build_positions(
        [
            trade("T1", TradeSide.BUY, "10", "10", "1"),
            trade("T2", TradeSide.BUY, "10", "20", "1"),
            trade("T3", TradeSide.SELL, "5", "30", "1"),
        ]
    )
    position = positions[0]
    assert position.quantity == Decimal("15")
    assert position.average_cost == Decimal("15.10")
    assert position.realized_pnl == Decimal("73.50")


def test_oversell_is_rejected() -> None:
    with pytest.raises(FinancialCalculationError, match="exceeds"):
        build_positions(
            [
                trade("T1", TradeSide.BUY, "1", "10"),
                trade("T2", TradeSide.SELL, "2", "10"),
            ]
        )


def test_cash_balance_includes_trades_and_cash_flows() -> None:
    portfolio = Portfolio(
        portfolio_id="P1",
        name="Reference",
        base_currency=USD,
        trades=(trade("T1", TradeSide.BUY, "2", "10", "1"),),
        cash_flows=(
            CashFlow(
                "F1",
                CashFlowKind.CONTRIBUTION,
                Decimal("100"),
                datetime(2026, 1, 1, tzinfo=UTC),
                USD,
            ),
            CashFlow(
                "F2",
                CashFlowKind.DIVIDEND,
                Decimal("5"),
                datetime(2026, 1, 2, tzinfo=UTC),
                USD,
                ASSET,
            ),
        ),
    )
    assert cash_balance(portfolio) == Decimal("84")
    assert aggregate_income_by_currency(portfolio.cash_flows) == {USD: Decimal("5")}


def test_portfolio_weights_and_valuation_reference() -> None:
    other = AssetId("XYZ", AssetClass.EQUITY, exchange="NYSE", currency=USD)
    other_trade = Trade(
        "T2",
        other,
        TradeSide.BUY,
        Decimal("1"),
        Decimal("20"),
        Decimal("0"),
        datetime(2026, 1, 2, tzinfo=UTC),
        USD,
    )
    portfolio = Portfolio(
        "P1",
        "Reference",
        USD,
        (trade("T1", TradeSide.BUY, "2", "10"), other_trade),
    )
    positions = build_positions(portfolio.trades)
    prices = {ASSET: Decimal("15"), other: Decimal("30")}
    weights = portfolio_weights(positions, prices)
    assert weights[ASSET] == pytest.approx(0.5)
    assert weights[other] == pytest.approx(0.5)

    snapshot = value_portfolio(
        portfolio,
        prices,
        as_of=datetime(2026, 1, 3, tzinfo=UTC),
        initial_cash=Decimal("100"),
    )
    assert snapshot.cash_balance == Decimal("60")
    assert snapshot.securities_market_value == Decimal("60")
    assert snapshot.total_value == Decimal("120")
    assert all(item.portfolio_weight == pytest.approx(0.25) for item in snapshot.positions)


def test_zero_value_portfolio_has_no_invented_weights() -> None:
    assert portfolio_weights([], {}) == {}
