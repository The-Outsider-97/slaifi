from fastapi.testclient import TestClient

from slaifi.application.contracts import (
    ReasoningRequest,
    ReasoningResult,
    ReasoningStatus,
)
from slaifi.core.config import Settings
from slaifi.main import create_app


class ProvenanceReasoner:
    def reason(self, request: ReasoningRequest) -> ReasoningResult:
        return ReasoningResult(
            status=ReasoningStatus.DEGRADED,
            interpretation="Evidence remains useful but validation is partial.",
            raw_result={"private": "not public"},
            agent="reasoning",
            agent_version="2.3.0",
            memory_key="slaifi:reasoning:result:private",
            correlation_id="corr-123",
            request_id=request.request_id,
            reasoning_strategy="cause_effect",
            confidence=0.68,
            outcome="indeterminate",
            degraded=True,
            validation_status="partial",
            warnings=("SLAI reasoning validation status: partial.",),
        )

    def status(self) -> ReasoningResult:
        return ReasoningResult(
            status=ReasoningStatus.AVAILABLE,
            interpretation=None,
            raw_result={"factory": {"private": True}},
            agent="reasoning",
            agent_version="2.3.0",
        )


def test_public_reasoning_response_exposes_safe_provenance_only() -> None:
    app = create_app(Settings(environment="test"), financial_reasoner=ProvenanceReasoner())
    payload = {
        "asset": {"symbol": "ABC", "currency": "USD"},
        "bars": [
            {
                "start_at": "2026-01-01T00:00:00+00:00",
                "end_at": "2026-01-02T00:00:00+00:00",
                "open": 100,
                "high": 102,
                "low": 99,
                "close": 101,
                "volume": 1000,
            },
            {
                "start_at": "2026-01-02T00:00:00+00:00",
                "end_at": "2026-01-03T00:00:00+00:00",
                "open": 101,
                "high": 103,
                "low": 100,
                "close": 102,
                "volume": 1100,
            },
        ],
        "periods_per_year": 252,
        "moving_average_period": 2,
        "momentum_period": 1,
        "rsi_period": 1,
        "atr_period": 1,
        "reasoning_objective": "Explain the measured state.",
    }
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/analysis/market",
            json=payload,
            headers={"X-Request-ID": "public-123"},
        )

    assert response.status_code == 200
    reasoning = response.json()["reasoning"]
    assert reasoning == {
        "status": "degraded",
        "interpretation": "Evidence remains useful but validation is partial.",
        "agent": "reasoning",
        "agent_version": "2.3.0",
        "correlation_id": "corr-123",
        "request_id": "public-123",
        "reasoning_strategy": "cause_effect",
        "confidence": 0.68,
        "outcome": "indeterminate",
        "degraded": True,
        "validation_status": "partial",
        "warnings": ["SLAI reasoning validation status: partial."],
    }
    assert "raw_result" not in reasoning
    assert "memory_key" not in reasoning
