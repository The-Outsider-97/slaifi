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
            raw_result={"result": f"reasoned:{request.operation}"},
            agent="reasoning",
            agent_version="test",
            correlation_id="portfolio-correlation",
            request_id=request.request_id,
        )

    def status(self) -> ReasoningResult:
        return ReasoningResult(status=ReasoningStatus.AVAILABLE, interpretation=None)


def test_portfolio_analysis_endpoint_integrates_financial_layers_and_reasoning() -> None:
    app = create_app(Settings(environment="test"), financial_reasoner=FakeReasoner())
    payload = {
        "portfolio": {
            "portfolio_id": "p1",
            "name": "Primary",
            "base_currency": "USD",
            "trades": [
                {
                    "trade_id": "t1",
                    "asset": {
                        "symbol": "ABC",
                        "exchange": "XNAS",
                        "currency": "USD",
                    },
                    "side": "buy",
                    "quantity": "2",
                    "unit_price": "100",
                    "fee": "1",
                    "occurred_at": "2026-01-01T00:00:00+00:00",
                    "currency": "USD",
                }
            ],
        },
        "prices": [
            {
                "asset": {
                    "symbol": "ABC",
                    "exchange": "XNAS",
                    "currency": "USD",
                },
                "price": "120",
            }
        ],
        "as_of": "2026-01-10T00:00:00+00:00",
        "initial_cash": "1000",
        "returns": [0.01, -0.005, 0.02, 0.004],
        "equity_values": [1000, 995, 1015, 1020],
        "periods_per_year": 252,
        "goal": {
            "goal_id": "growth",
            "return_target": {"annual_rate": 0.10},
        },
        "assumed_annual_return_rate": 0.08,
        "reasoning_objective": "Assess the portfolio against the supplied goal.",
    }
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/analysis/portfolio",
            json=payload,
            headers={"X-Request-ID": "portfolio-request"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"]["total_value"] == "1039"
    assert body["risk"]["observation_count"] == 4
    assert body["goals"]["returns"]["annual_rate_gap"] == -0.02
    reasoning = body["reasoning"]
    assert reasoning["interpretation"] == "reasoned:portfolio_analysis"
    assert reasoning["request_id"] == "portfolio-request"
    assert reasoning["correlation_id"] == "portfolio-correlation"
    assert "raw_result" not in reasoning


def test_portfolio_analysis_endpoint_rejects_future_ledger_event() -> None:
    app = create_app(Settings(environment="test"), financial_reasoner=FakeReasoner())
    payload = {
        "portfolio": {
            "portfolio_id": "p1",
            "name": "Primary",
            "base_currency": "USD",
            "trades": [
                {
                    "trade_id": "future",
                    "asset": {"symbol": "ABC", "currency": "USD"},
                    "side": "buy",
                    "quantity": "1",
                    "unit_price": "100",
                    "fee": "0",
                    "occurred_at": "2026-02-01T00:00:00+00:00",
                    "currency": "USD",
                }
            ],
        },
        "prices": [
            {
                "asset": {"symbol": "ABC", "currency": "USD"},
                "price": "110",
            }
        ],
        "as_of": "2026-01-31T00:00:00+00:00",
        "initial_cash": "1000",
    }
    with TestClient(app) as client:
        response = client.post("/api/v1/analysis/portfolio", json=payload)

    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"
