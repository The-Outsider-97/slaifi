import pytest

from slaifi.application.contracts import (
    ReasoningRequest,
    ReasoningStatus,
    ReasoningUnavailableError,
)
from slaifi.integrations.slai import SlaiFinancialReasoner


class FakeMemory:
    def __init__(self) -> None:
        self.writes: list[tuple[str, object, dict[str, object]]] = []

    def set(self, key: str, value: object, **kwargs: object) -> None:
        self.writes.append((key, value, dict(kwargs)))


class FakeAgent:
    version = "test-1"

    def __init__(self) -> None:
        self.calls: list[tuple[object, object, object]] = []

    def reason(self, problem: object, reasoning_type: object = None, context: object = None):
        self.calls.append((problem, reasoning_type, context))
        return {"result": "Evidence is mixed; uncertainty remains.", "confidence": 0.7}

    def runtime_status(self):
        return {"health": "healthy"}


class FakeFactory:
    def __init__(self, agent: FakeAgent) -> None:
        self.agent = agent
        self.calls: list[tuple[str, object]] = []

    def create(self, agent_type: str, shared_memory: object = None):
        self.calls.append((agent_type, shared_memory))
        return self.agent


class FailingFactory:
    def create(self, agent_type: str, shared_memory: object = None):
        raise RuntimeError("factory unavailable")


def test_slai_adapter_uses_factory_shared_memory_and_authoritative_evidence() -> None:
    memory = FakeMemory()
    agent = FakeAgent()
    factory = FakeFactory(agent)
    adapter = SlaiFinancialReasoner(factory=factory, shared_memory=memory)
    result = adapter.reason(
        ReasoningRequest(
            operation="market_analysis",
            evidence={"latest_return_rate": 0.05},
            objective="Interpret the evidence.",
            assumptions={"periods_per_year": 252},
            uncertainty={"prediction_model_used": False},
            correlation_id="abc",
        )
    )
    assert result.status is ReasoningStatus.AVAILABLE
    assert result.interpretation == "Evidence is mixed; uncertainty remains."
    assert factory.calls == [("reasoning", memory)]
    assert len(memory.writes) == 2
    assert memory.writes[0][0] == "slaifi:reasoning:request:abc"
    assert memory.writes[1][0] == "slaifi:reasoning:result:abc"
    context = agent.calls[0][2]
    assert context["authoritative_evidence"]["latest_return_rate"] == 0.05
    assert "Do not alter" in context["instruction"]


def test_optional_slai_runtime_degrades_without_breaking_financial_layer() -> None:
    adapter = SlaiFinancialReasoner(factory=FailingFactory(), shared_memory=FakeMemory())
    result = adapter.reason(
        ReasoningRequest(operation="test", evidence={}, objective="interpret")
    )
    assert result.status is ReasoningStatus.UNAVAILABLE


def test_required_slai_runtime_fails_explicitly() -> None:
    adapter = SlaiFinancialReasoner(
        factory=FailingFactory(),
        shared_memory=FakeMemory(),
        required=True,
    )
    with pytest.raises(ReasoningUnavailableError):
        adapter.reason(ReasoningRequest(operation="test", evidence={}, objective="interpret"))
