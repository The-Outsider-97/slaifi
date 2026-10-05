from typing import Any

from slaifi.application.contracts import ReasoningRequest, ReasoningStatus
from slaifi.integrations.slai import SlaiFinancialReasoner


class Memory:
    def __init__(self) -> None:
        self.writes: list[tuple[str, object, dict[str, object]]] = []

    def set(self, key: str, value: object, **kwargs: object) -> None:
        self.writes.append((key, value, dict(kwargs)))


class ReasoningAgent:
    version = "reasoning-test"

    def reason(
        self,
        problem: object,
        reasoning_type: object = None,
        context: object = None,
    ) -> dict[str, object]:
        return {
            "conclusion": "Maintain diversification; evidence is mixed.",
            "confidence": {"value": 0.7},
            "outcome": "supported",
            "validation": {"validation_status": "passed"},
            "selection": {"resolved": "cause_effect"},
        }

    def runtime_status(self) -> dict[str, str]:
        return {"health": "healthy"}


class QualityAgent:
    def perform_task(self, task_data: dict[str, Any]) -> dict[str, object]:
        return {"verdict": "pass", "quality_verdict": "pass"}


class SafetyAgent:
    def __init__(self, decision: str = "allow", *, fail: bool = False) -> None:
        self.decision = decision
        self.fail = fail
        self.calls: list[tuple[object, object]] = []

    def perform_task(self, data_to_assess: object, context: object = None) -> dict[str, object]:
        self.calls.append((data_to_assess, context))
        if self.fail:
            raise RuntimeError("safety unavailable")
        return {
            "decision": self.decision,
            "is_safe": self.decision == "allow",
            "risk_level": "low" if self.decision == "allow" else "medium",
        }


class Factory:
    def __init__(self, safety: SafetyAgent) -> None:
        self.reasoning = ReasoningAgent()
        self.quality = QualityAgent()
        self.safety = safety
        self.calls: list[str] = []

    def create(self, agent_type: str, shared_memory: object = None) -> object:
        self.calls.append(agent_type)
        if agent_type == "reasoning":
            return self.reasoning
        if agent_type == "quality":
            return self.quality
        if agent_type == "safety":
            return self.safety
        raise AssertionError(agent_type)


def _request() -> ReasoningRequest:
    return ReasoningRequest(
        operation="portfolio_analysis",
        objective="Interpret the portfolio.",
        evidence={
            "portfolio_id": "private-portfolio-id",
            "positions": [{"asset": "ABC", "market_value": "1200.00"}],
        },
    )


def _adapter(safety: SafetyAgent) -> SlaiFinancialReasoner:
    return SlaiFinancialReasoner(
        factory=Factory(safety),
        shared_memory=Memory(),
        quality_enabled=True,
        safety_enabled=True,
    )


def test_safety_allow_preserves_interpretation_and_provenance() -> None:
    safety = SafetyAgent("allow")
    result = _adapter(safety).reason(_request())

    assert result.status is ReasoningStatus.AVAILABLE
    assert result.interpretation == "Maintain diversification; evidence is mixed."
    assert result.safety_status == "allow"
    assert result.safety_agent == "safety"
    assert result.validation_status == "passed"


def test_safety_receives_interpretation_not_authoritative_portfolio_evidence() -> None:
    safety = SafetyAgent("allow")
    _adapter(safety).reason(_request())

    assert len(safety.calls) == 1
    payload, context = safety.calls[0]
    assert payload == {"text": "Maintain diversification; evidence is mixed."}
    assert isinstance(context, dict)
    assert context["financial_facts_included"] is False
    assert context["user_portfolio_data_included"] is False
    assert "private-portfolio-id" not in repr((payload, context))
    assert "market_value" not in repr((payload, context))


def test_safety_review_degrades_but_keeps_interpretation() -> None:
    result = _adapter(SafetyAgent("review")).reason(_request())

    assert result.status is ReasoningStatus.DEGRADED
    assert result.interpretation is not None
    assert result.safety_status == "review"
    assert result.validation_status == "partial"
    assert any("safety gate requires review" in item.lower() for item in result.warnings)


def test_safety_block_hides_ai_interpretation_without_touching_financial_result() -> None:
    result = _adapter(SafetyAgent("block")).reason(_request())

    assert result.status is ReasoningStatus.DEGRADED
    assert result.interpretation is None
    assert result.safety_status == "block"
    assert result.validation_status == "failed"
    assert any("safety gate blocked" in item.lower() for item in result.warnings)


def test_safety_unavailable_is_explicitly_degraded() -> None:
    result = _adapter(SafetyAgent(fail=True)).reason(_request())

    assert result.status is ReasoningStatus.DEGRADED
    assert result.interpretation is not None
    assert result.safety_status == "review"
    assert result.validation_status == "partial"
