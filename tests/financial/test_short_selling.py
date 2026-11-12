"""Simulated short selling: signed positions, collateral, strategy limits and every refusal."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.api.test_finance_api import H, create_app, make_portfolio, settings
from tests.financial.test_paper_execution import (
    ASSET,
    COSTS,
    NOW,
    USD,
    codes,
    order,
    quote,
    run,
)

from slaifi.domain.paper import ExecutionPolicy, OrderStatus, RejectionCode
from slaifi.domain.portfolio import (
    SHORT_MARGIN_RATE,
    Portfolio,
    PortfolioSnapshot,
    Position,
    PositionValuation,
    Trade,
    TradeSide,
)
from slaifi.domain.recommendations import RecommendationAction
from slaifi.domain.strategies import instantiate_preset
from slaifi.engines.paper import evaluate_order
from slaifi.engines.portfolio import build_positions, cash_balance, value_portfolio
from slaifi.engines.recommendation.rules import choose_action
from slaifi.engines.utils.errors import FinancialCalculationError

D = Decimal


def trade(
    tid: str, side: TradeSide, qty: str, price: str, fee: str = "0", minutes: int = 0
) -> Trade:
    return Trade(tid, ASSET, side, D(qty), D(price), D(fee), NOW + timedelta(minutes=minutes), USD)


def ledger(*trades: Trade) -> Portfolio:
    return Portfolio("p", "P", USD, trades=tuple(trades))


# ------------------------------------------------------------------ accounting
def test_short_then_cover_realises_the_difference_and_closes() -> None:
    book = ledger(
        trade("1", TradeSide.SHORT, "10", "100", fee="1", minutes=0),
        trade("2", TradeSide.COVER, "10", "80", fee="1", minutes=1),
    )
    (pos,) = build_positions(book.trades)
    assert pos.quantity == 0 and pos.average_cost == 0
    # received 1000 - 1, paid 800 + 1  => +198
    assert pos.realized_pnl == D("198")
    assert cash_balance(book, initial_cash=D("5000")) == D("5198")


def test_open_short_is_a_negative_signed_position_valued_as_a_liability() -> None:
    book = ledger(trade("1", TradeSide.SHORT, "10", "100"))
    (pos,) = build_positions(book.trades)
    assert pos.quantity == D("-10") and pos.is_short and pos.average_cost == D("100")
    snap = value_portfolio(book, {ASSET: D("90")}, as_of=NOW, initial_cash=D("5000"))
    (val,) = snap.positions
    assert val.market_value == D("-900") and val.unrealized_pnl == D("100")  # price fell: gain
    assert snap.cash_balance == D("6000") and snap.securities_market_value == D("-900")
    assert snap.total_value == D("5100") and snap.short_value == D("900")
    assert snap.margin_required == D("900") * SHORT_MARGIN_RATE
    assert snap.free_cash == D("6000") - D("1350")
    rising = value_portfolio(book, {ASSET: D("120")}, as_of=NOW, initial_cash=D("5000"))
    assert rising.positions[0].unrealized_pnl == D("-200") and rising.total_value == D("4800")


def test_partial_cover_keeps_average_and_the_rest_of_the_short() -> None:
    book = ledger(
        trade("1", TradeSide.SHORT, "10", "100"),
        trade("2", TradeSide.SHORT, "10", "110", minutes=1),
        trade("3", TradeSide.COVER, "5", "90", minutes=2),
    )
    (pos,) = build_positions(book.trades)
    assert pos.quantity == D("-15") and pos.average_cost == D("105")
    assert pos.realized_pnl == D("75")  # (105 - 90) * 5


@pytest.mark.parametrize(
    "bad",
    [
        (TradeSide.SELL, "1"),  # selling a short
        (TradeSide.BUY, "1"),  # buying a short
    ],
)
def test_ledger_refuses_the_wrong_direction_on_a_short(bad: tuple[TradeSide, str]) -> None:
    with pytest.raises(FinancialCalculationError):
        build_positions(
            ledger(
                trade("1", TradeSide.SHORT, "5", "10"), trade("2", bad[0], bad[1], "10", minutes=1)
            ).trades
        )


def test_ledger_refuses_shorting_a_long_and_covering_nothing() -> None:
    with pytest.raises(FinancialCalculationError):
        build_positions(
            ledger(
                trade("1", TradeSide.BUY, "5", "10"),
                trade("2", TradeSide.SHORT, "1", "10", minutes=1),
            ).trades
        )
    with pytest.raises(FinancialCalculationError):
        build_positions(ledger(trade("1", TradeSide.COVER, "1", "10")).trades)
    with pytest.raises(FinancialCalculationError):
        build_positions(
            ledger(
                trade("1", TradeSide.SHORT, "2", "10"),
                trade("2", TradeSide.COVER, "3", "10", minutes=1),
            ).trades
        )


# ------------------------------------------------------------------ execution rules
def snap_with_short(cash: str = "10000", qty: str = "-10", price: str = "60") -> PortfolioSnapshot:
    pos = Position(ASSET, D(qty), D("60"), D("0"), USD)
    value = D(qty) * D(price)
    val = PositionValuation(pos, D(price), value, D("0"), float(value / (D(cash) + value)))
    return PortfolioSnapshot("p", NOW, USD, D(cash), (val,), value, D(cash) + value)


def tactical():  # type: ignore[no-untyped-def]
    return instantiate_preset("tactical_long_short", strategy_id="t", name="t")


def run_with(strategy, req, snap, q=None):  # type: ignore[no-untyped-def]
    return evaluate_order(
        req,
        snapshot=snap,
        quote=q or quote(),
        policy=ExecutionPolicy(),
        costs=COSTS,
        now=NOW,
        trade_id="t1",
        strategy=strategy,
        annualized_volatility=0.2,
    )


def empty(cash: str = "10000") -> PortfolioSnapshot:
    return PortfolioSnapshot("p", NOW, USD, D(cash), (), D("0"), D(cash))


def test_short_is_refused_while_the_strategy_leaves_it_off() -> None:
    decision = run(order(side=TradeSide.SHORT), quote())  # default preset: short exposure 0
    assert decision.status is OrderStatus.REJECTED
    assert RejectionCode.SHORT_NOT_ALLOWED in codes(decision)
    assert "switched off" in decision.rejections[0].message


def test_short_fills_under_a_strategy_that_allows_it_with_slippage_against_the_seller() -> None:
    decision = run_with(tactical(), order(side=TradeSide.SHORT, quantity=D("15")), empty())
    assert decision.status is OrderStatus.FILLED, decision.rejections
    ex = decision.execution
    assert ex is not None and ex.execution_price < ex.quote_price  # sellers receive less
    assert ex.net_cash_effect > 0 and ex.gross_amount == D("899.55")
    assert any("borrow fees" in w for w in decision.warnings)


def test_short_over_the_exposure_limit_is_refused() -> None:
    # 25 % of 10 000 is 2 500; 60 * 50 = 3 000 > limit
    decision = run_with(tactical(), order(side=TradeSide.SHORT, quantity=D("50")), empty())
    assert decision.status is OrderStatus.REJECTED
    assert any("short" in r.message.lower() and "limit" in r.message for r in decision.rejections)


def test_short_needs_collateral() -> None:
    strategy = tactical()
    # Position cap 10 % would also bite, so raise it out of the way and starve the margin instead.
    from dataclasses import replace

    from slaifi.domain.goals import RiskConstraints

    loose = replace(
        strategy,
        constraints=replace(strategy.constraints, max_position_weight=1.0, max_short_exposure=1.0),
        cash_reserve_rate=0.0,
        max_concentration_hhi=None,
    )
    # cash 1 000, short of 10 x 60 = 600: collateral 150 % = 900; cash after = 1 000 + 599 > 900 ok
    ok = run_with(loose, order(side=TradeSide.SHORT, quantity=D("10")), empty("1000"))
    assert ok.status is OrderStatus.FILLED
    # short of 40 x 60 = 2 400: collateral 3 600 > 1 000 + 2 399
    bad = run_with(loose, order(side=TradeSide.SHORT, quantity=D("40")), empty("1000"))
    assert RejectionCode.INSUFFICIENT_MARGIN in codes(bad)
    assert RiskConstraints  # keep the import honest


def test_cannot_short_a_long_position_or_sell_a_short() -> None:
    long_pos = Position(ASSET, D("5"), D("60"), D("0"), USD)
    long_val = PositionValuation(long_pos, D("60"), D("300"), D("0"), 0.03)
    long_snap = PortfolioSnapshot("p", NOW, USD, D("9700"), (long_val,), D("300"), D("10000"))
    assert RejectionCode.WRONG_DIRECTION in codes(
        run_with(tactical(), order(side=TradeSide.SHORT, quantity=D("1")), long_snap)
    )
    assert RejectionCode.WRONG_DIRECTION in codes(
        run_with(tactical(), order(side=TradeSide.SELL, quantity=D("1")), snap_with_short())
    )
    assert RejectionCode.WRONG_DIRECTION in codes(
        run_with(tactical(), order(side=TradeSide.BUY, quantity=D("1")), snap_with_short())
    )


def test_selling_more_than_held_points_to_short() -> None:
    decision = run(order(side=TradeSide.SELL, quantity=D("5")), quote())
    assert RejectionCode.INSUFFICIENT_POSITION in codes(decision)
    assert "Short" in decision.rejections[0].message


def test_cover_reduces_or_closes_and_is_never_blocked_by_exposure_limits() -> None:
    snap = snap_with_short()
    part = run_with(tactical(), order(side=TradeSide.COVER, quantity=D("4")), snap)
    assert part.status is OrderStatus.FILLED and part.execution is not None
    assert part.execution.execution_price > part.execution.quote_price  # covers pay more
    assert part.execution.net_cash_effect < 0
    close = run_with(
        instantiate_preset("steady_accumulation", strategy_id="s", name="s"),  # shorting off
        order(side=TradeSide.COVER, close_position=True, quantity=None),
        snap,
    )
    assert close.status is OrderStatus.FILLED and close.trade is not None
    assert close.trade.quantity == D("10")
    assert RejectionCode.INSUFFICIENT_POSITION in codes(
        run_with(tactical(), order(side=TradeSide.COVER, quantity=D("11")), snap)
    )
    assert RejectionCode.INSUFFICIENT_POSITION in codes(
        run_with(tactical(), order(side=TradeSide.COVER, quantity=D("1")), empty())
    )


def test_collateral_is_not_available_for_buying() -> None:
    from slaifi.domain.assets import AssetClass, AssetId

    other = AssetId("PG", AssetClass.EQUITY, "NYSE", USD)
    snap = snap_with_short(cash="10600", qty="-10", price="60")  # margin 900, free 9 700
    decision = run_with(
        tactical(),
        order(
            asset=other, side=TradeSide.BUY, quantity=D("165")
        ),  # ~9 900: within cash, beyond free cash
        snap,
        quote(asset=other, price=D("60")),
    )
    assert RejectionCode.INSUFFICIENT_CASH in codes(decision)
    assert any("collateral" in r.message for r in decision.rejections)


def test_close_position_direction_matches_the_side() -> None:
    snap = snap_with_short()
    wrong = run_with(
        tactical(), order(side=TradeSide.SELL, close_position=True, quantity=None), snap
    )
    assert wrong.status is OrderStatus.REJECTED


# ------------------------------------------------------------------ recommendation rules
def test_short_is_only_recommended_when_the_strategy_allows_it() -> None:
    strategy = tactical()
    kwargs = dict(
        strategy=strategy, holding=False, eligibility_blocked=False, purchase_blocked=False
    )
    action, reason = choose_action(-0.9, short_allowed=True, **kwargs)  # type: ignore[arg-type]
    assert action is RecommendationAction.SHORT and "can lose more" in reason
    assert choose_action(-0.9, short_allowed=False, **kwargs)[0] is RecommendationAction.AVOID  # type: ignore[arg-type]


def test_short_held_is_covered_when_signals_turn_and_never_shorted_again() -> None:
    strategy = tactical()
    base = dict(strategy=strategy, holding=False, eligibility_blocked=False, purchase_blocked=False)
    assert choose_action(0.9, short_holding=True, **base)[0] is RecommendationAction.COVER  # type: ignore[arg-type]
    assert (
        choose_action(-0.9, short_holding=True, short_allowed=True, **base)[0]
        is RecommendationAction.HOLD
    )  # type: ignore[arg-type]
    assert choose_action(0.2, short_holding=True, **base)[0] is RecommendationAction.HOLD  # type: ignore[arg-type]
    assert (
        choose_action(0.0, short_holding=True, **{**base, "eligibility_blocked": True})[0]  # type: ignore[arg-type]
        is RecommendationAction.COVER
    )


# ------------------------------------------------------------------ the whole thing over HTTP
@pytest.fixture()
def client(tmp_path: Path) -> Any:
    with TestClient(create_app(settings(tmp_path)), raise_server_exceptions=False) as c:
        yield c


def _short_capable_portfolio(c: TestClient) -> str:
    made = c.post(
        "/api/v1/strategies",
        headers=H,
        json={"name": "LS", "preset_id": "tactical_long_short", "activate": True},
    )
    assert made.status_code in {200, 201}, made.text
    sid = made.json()["strategy_id"]
    r = c.post(
        "/api/v1/paper/portfolios",
        headers=H,
        json={"name": "LS", "starting_capital": "10000", "strategy_id": sid},
    )
    assert r.status_code == 201, r.text
    return str(r.json()["portfolio"]["portfolio_id"])


def test_short_and_cover_end_to_end(client: TestClient) -> None:
    pid = _short_capable_portfolio(client)
    url = f"/api/v1/paper/portfolios/{pid}/orders"
    opened = client.post(
        url, headers=H, json={"symbol": "KO", "side": "short", "quantity": "5"}
    ).json()
    assert opened["decision"]["status"] == "filled", opened["decision"]["rejections"]
    view = client.get(f"/api/v1/paper/portfolios/{pid}").json()
    (pos,) = view["positions"]
    assert pos["direction"] == "short" and float(pos["quantity"]) == -5.0
    assert float(pos["market_value"]) < 0 and float(view["short_value"]) > 0
    assert float(view["margin_required"]) == pytest.approx(
        float(view["short_value"]) * 1.5, rel=1e-6
    )
    assert float(view["free_cash"]) < float(view["cash_balance"])
    # buying back more than is short, then the whole position
    assert (
        client.post(url, headers=H, json={"symbol": "KO", "side": "cover", "quantity": "6"}).json()[
            "decision"
        ]["status"]
        == "rejected"
    )
    closed = client.post(
        url, headers=H, json={"symbol": "KO", "side": "cover", "close_position": True}
    ).json()
    assert closed["decision"]["status"] == "filled"
    after = client.get(f"/api/v1/paper/portfolios/{pid}").json()
    assert after["positions"] == [] and float(after["short_value"]) == 0.0
    check = client.get(f"/api/v1/paper/portfolios/{pid}/reconcile").json()
    assert check["consistent"] is True and check["issues"] == []


def test_short_is_off_on_the_default_strategy_over_http(client: TestClient) -> None:
    pid = make_portfolio(client)
    r = client.post(
        f"/api/v1/paper/portfolios/{pid}/orders",
        headers=H,
        json={"symbol": "KO", "side": "short", "quantity": "1"},
    ).json()
    assert r["decision"]["status"] == "rejected"
    assert r["decision"]["rejections"][0]["code"] == "short_not_allowed"
    assert client.get(f"/api/v1/paper/portfolios/{pid}").json()["positions"] == []


def test_raising_the_short_limit_needs_acknowledgement(client: TestClient) -> None:
    assert client.get("/api/v1/strategies/default").json()["max_short_exposure"] == 0.0
    refused = client.patch(
        "/api/v1/strategies/default", headers=H, json={"fields": {"max_short_exposure": 0.2}}
    )
    assert refused.status_code in {409, 422}
    ok = client.patch(
        "/api/v1/strategies/default",
        headers=H,
        json={"fields": {"max_short_exposure": 0.2}, "acknowledge_loosening": True},
    )
    assert ok.status_code == 200 and ok.json()["max_short_exposure"] == pytest.approx(0.2)
    # tightening back never needs it
    assert (
        client.patch(
            "/api/v1/strategies/default", headers=H, json={"fields": {"max_short_exposure": 0.0}}
        ).status_code
        == 200
    )


def test_advisor_reads_short_and_cover_orders(client: TestClient) -> None:
    pid = make_portfolio(client)
    proposal = client.post(
        "/api/v1/advisor/interpret",
        headers=H,
        json={"text": "short 5 shares of KO", "portfolio_id": pid},
    ).json()
    drafts = [o for o in proposal.get("orders", [])]
    assert drafts and drafts[0]["draft"]["side"] == "short"
    cover = client.post(
        "/api/v1/advisor/interpret",
        headers=H,
        json={"text": "cover all of my KO", "portfolio_id": pid},
    ).json()
    assert (
        cover["orders"][0]["draft"]["side"] == "cover"
        and cover["orders"][0]["draft"]["close_position"]
    )
