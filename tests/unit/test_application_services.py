from datetime import UTC, datetime, timedelta
from decimal import Decimal

from slaifi.application.analysis import AnalyzeMarketSeries, AnalyzePortfolio
from slaifi.application.contracts import (
    ReasoningRequest,
    ReasoningResult,
    ReasoningStatus,
)
from slaifi.application.goals import EvaluateFinancialGoal
from slaifi.domain.assets import AssetId
from slaifi.domain.goals import FinancialGoal, IncomePeriod, IncomeTarget, ReturnTarget
from slaifi.domain.market import OHLCVBar
from slaifi.domain.portfolio import Portfolio, Trade, TradeSide


class RecordingReasoner:
    def __init__(self) -> None:
        self.requests: list[ReasoningRequest] = []

    def reason(self, request: ReasoningRequest) -> ReasoningResult:
        self.requests.append(request)
        return ReasoningResult(
            status=ReasoningStatus.AVAILABLE,
            interpretation="Contextual interpretation only.",
            raw_result={"result": "Contextual interpretation only."},
            agent="reasoning",
            correlation_id="test-correlation",
            request_id=request.request_id,
        )

    def status(self) -> ReasoningResult:
        return ReasoningResult(
            status=ReasoningStatus.AVAILABLE,
            interpretation=None,
        )


def _bars(asset: AssetId, count: int = 40) -> tuple[OHLCVBar, ...]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    output = []
    for index in range(count):
        price = Decimal(100 + index)
        bar_start = start + timedelta(days=index)
        output.append(
            OHLCVBar(
                asset=asset,
                start_at=bar_start,
                end_at=bar_start + timedelta(days=1),
                open=price,
                high=price + Decimal("2"),
                low=price - Decimal("1"),
                close=price + Decimal("1"),
                volume=Decimal(1000 + index * 10),
            )
        )
    return tuple(output)


def test_market_analysis_keeps_reasoning_separate_from_calculations() -> None:
    reasoner = RecordingReasoner()
    asset = AssetId("ABC", exchange="XNAS")
    result = AnalyzeMarketSeries(reasoner).execute(
        asset,
        _bars(asset),
        periods_per_year=252,
        moving_average_period=5,
        momentum_period=5,
        rsi_period=5,
        atr_period=5,
        reasoning_objective="Explain the measured market state.",
        request_id="market-request",
    )
    assert result.latest_close == 140.0
    assert result.technical.sma is not None
    assert result.reasoning is not None
    assert result.reasoning.interpretation == "Contextual interpretation only."
    assert len(reasoner.requests) == 1
    request = reasoner.requests[0]
    assert request.evidence["latest_close"] == 140.0
    assert request.uncertainty["prediction_model_used"] is False
    assert request.request_id == "market-request"


def test_portfolio_analysis_composes_valuation_risk_goal_and_reasoning() -> None:
    reasoner = RecordingReasoner()
    asset = AssetId("ABC", exchange="XNAS", currency="USD")
    portfolio = Portfolio(
        portfolio_id="p1",
        name="Primary",
        base_currency="USD",
        trades=(
            Trade(
                trade_id="t1",
                asset=asset,
                side=TradeSide.BUY,
                quantity=Decimal("2"),
                unit_price=Decimal("100"),
                fee=Decimal("1"),
                occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
                currency="USD",
            ),
        ),
    )
    result = AnalyzePortfolio(reasoner).execute(
        portfolio,
        {asset: Decimal("120")},
        as_of=datetime(2026, 1, 10, tzinfo=UTC),
        initial_cash=Decimal("1000"),
        returns=[0.01, -0.005, 0.02, 0.004],
        equity_values=[1000, 995, 1015, 1020],
        periods_per_year=252,
        goal=FinancialGoal("g1", return_target=ReturnTarget(0.10)),
        assumed_annual_return_rate=0.08,
        reasoning_objective="Assess alignment with the stated goal.",
        request_id="portfolio-request",
    )
    assert result.snapshot.total_value == Decimal("1039")
    assert result.risk is not None
    assert result.goals is not None
    assert result.goals.returns is not None
    assert result.goals.returns.annual_rate_gap == -0.02
    assert result.reasoning is not None
    assert reasoner.requests[0].operation == "portfolio_analysis"
    assert reasoner.requests[0].request_id == "portfolio-request"


def test_goal_service_reuses_authoritative_goal_arithmetic_before_reasoning() -> None:
    reasoner = RecordingReasoner()
    goal = FinancialGoal(
        "income",
        income_target=IncomeTarget(Decimal("150"), IncomePeriod.WEEKLY),
    )
    result = EvaluateFinancialGoal(reasoner).execute(
        goal,
        available_capital=Decimal("50000"),
        assumed_annual_income_yield_rate=0.05,
        reasoning_objective="Explain the feasibility result.",
        request_id="goal-request",
    )
    assert result.evaluation.income is not None
    assert result.evaluation.income.annual_income_target == Decimal("7800")
    assert result.evaluation.income.required_yield_rate == 0.156
    assert result.reasoning is not None
    assert reasoner.requests[0].operation == "goal_evaluation"
    assert reasoner.requests[0].request_id == "goal-request"
