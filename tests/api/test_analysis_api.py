from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from slaifi.application.contracts import ReasoningRequest, ReasoningResult, ReasoningStatus
from slaifi.core.config import Settings
from slaifi.main import create_app


class FakeReasoner:
    def reason(self, request: ReasoningRequest) -> ReasoningResult:
        return ReasoningResult(
            status=ReasoningStatus.AVAILABLE,
            interpretation=f"reasoned:{request.operation}",
            raw_result={"result": f"reasoned:{request.operation}"},
            agent="reasoning",
            agent_version="test",
        )

    def status(self) -> ReasoningResult:
        return ReasoningResult(
            status=ReasoningStatus.AVAILABLE,
            interpretation=None,
            agent="reasoning",
            agent_version="test",
        )


def _market_payload() -> dict:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    bars = []
    for index in range(40):
        price = 100 + index
        bar_start = start + timedelta(days=index)
        bars.append(
            {
                "start_at": bar_start.isoformat(),
                "end_at": (bar_start + timedelta(days=1)).isoformat(),
                "open": price,
                "high": price + 2,
                "low": price - 1,
                "close": price + 1,
                "volume": 1000 + index,
            }
        )
    return {
        "asset": {"symbol": "ABC", "exchange": "XNAS", "currency": "USD"},
        "bars": bars,
        "periods_per_year": 252,
        "moving_average_period": 5,
        "momentum_period": 5,
        "rsi_period": 5,
        "atr_period": 5,
        "reasoning_objective": "Explain the measured state.",
    }


def test_market_analysis_endpoint_separates_calculation_and_reasoning() -> None:
    app = create_app(Settings(environment="test"), financial_reasoner=FakeReasoner())
    with TestClient(app) as client:
        response = client.post("/api/v1/analysis/market", json=_market_payload())
    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_close"] == 140.0
    assert payload["reasoning"]["interpretation"] == "reasoned:market_analysis"
    assert payload["features"]["simple_returns"][0] is None


def test_goal_endpoint_reports_incompatible_income_target_arithmetic() -> None:
    app = create_app(Settings(environment="test"), financial_reasoner=FakeReasoner())
    request = {
        "goal": {
            "goal_id": "income",
            "income_target": {"amount": "150", "period": "weekly"},
        },
        "available_capital": "50000",
        "assumed_annual_income_yield_rate": 0.05,
    }
    with TestClient(app) as client:
        response = client.post("/api/v1/goals/evaluate", json=request)
    assert response.status_code == 200
    payload = response.json()["income"]
    assert payload["annual_income_target"] == "7800"
    assert payload["required_yield_rate"] == 0.156
    assert payload["status"] == "not_feasible_under_assumptions"


def test_slai_status_endpoint_reports_injected_runtime() -> None:
    app = create_app(Settings(environment="test"), financial_reasoner=FakeReasoner())
    with TestClient(app) as client:
        response = client.get("/api/v1/integrations/slai")
    assert response.status_code == 200
    assert response.json()["status"] == "available"
