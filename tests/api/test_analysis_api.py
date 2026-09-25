from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from slaifi.application.contracts import (
    ReasoningRequest,
    ReasoningResult,
    ReasoningStatus,
)
from slaifi.core.config import Settings
from slaifi.main import create_app


class FakeReasoner:
    def reason(self, request: ReasoningRequest) -> ReasoningResult:
        return ReasoningResult(
            status=ReasoningStatus.AVAILABLE,
            interpretation=f"reasoned:{request.operation}",
            raw_result={"result": f"reasoned:{request.operation}", "private": "internal"},
            agent="reasoning",
            agent_version="test",
            memory_key="slaifi:reasoning:result:internal",
            correlation_id="corr-test",
            request_id=request.request_id,
        )

    def status(self) -> ReasoningResult:
        return ReasoningResult(
            status=ReasoningStatus.AVAILABLE,
            interpretation=None,
            raw_result={"factory": {"health": "healthy"}},
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
        response = client.post(
            "/api/v1/analysis/market",
            json=_market_payload(),
            headers={"X-Request-ID": "client-42"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_close"] == 140.0
    reasoning = payload["reasoning"]
    assert reasoning["interpretation"] == "reasoned:market_analysis"
    assert reasoning["correlation_id"] == "corr-test"
    assert reasoning["request_id"] == "client-42"
    assert "raw_result" not in reasoning
    assert "memory_key" not in reasoning
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
    body = response.json()
    payload = body["evaluation"]["income"]
    assert payload["annual_income_target"] == "7800"
    assert payload["required_yield_rate"] == 0.156
    assert payload["status"] == "not_feasible_under_assumptions"
    assert body["reasoning"] is None


def test_goal_endpoint_can_add_separate_slai_interpretation() -> None:
    app = create_app(Settings(environment="test"), financial_reasoner=FakeReasoner())
    request = {
        "goal": {
            "goal_id": "income",
            "income_target": {"amount": "150", "period": "weekly"},
        },
        "available_capital": "50000",
        "assumed_annual_income_yield_rate": 0.05,
        "reasoning_objective": "Explain the feasibility result.",
    }
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/goals/evaluate",
            json=request,
            headers={"X-Request-ID": "goal-request"},
        )
    assert response.status_code == 200
    reasoning = response.json()["reasoning"]
    assert reasoning["interpretation"] == "reasoned:goal_evaluation"
    assert reasoning["request_id"] == "goal-request"


def test_slai_status_endpoint_reports_injected_runtime_without_raw_payload() -> None:
    app = create_app(Settings(environment="test"), financial_reasoner=FakeReasoner())
    with TestClient(app) as client:
        response = client.get("/api/v1/integrations/slai")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "available"
    assert "raw_result" not in payload
    assert "memory_key" not in payload


def test_blank_request_id_is_rejected() -> None:
    app = create_app(Settings(environment="test"), financial_reasoner=FakeReasoner())
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/analysis/market",
            json=_market_payload(),
            headers={"X-Request-ID": "   "},
        )
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"
