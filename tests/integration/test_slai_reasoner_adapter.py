from types import SimpleNamespace

import pytest

import slaifi.integrations.slai.reasoner as reasoner_module
from slaifi.application.contracts import (
    ReasoningRequest,
    ReasoningStatus,
    ReasoningUnavailableError,
)
from slaifi.core.exceptions import ConfigurationError
from slaifi.integrations.slai import SlaiFinancialReasoner


class FakeMemory:
    def __init__(self) -> None:
        self.writes: list[tuple[str, object, dict[str, object]]] = []
        self.closed = False

    def set(self, key: str, value: object, **kwargs: object) -> None:
        self.writes.append((key, value, dict(kwargs)))

    def health_check(self) -> dict[str, object]:
        return {"status": "ok", "health": "healthy", "item_count": len(self.writes)}

    def close(self) -> None:
        self.closed = True


class FakeAgent:
    version = "test-1"

    def __init__(self) -> None:
        self.calls: list[tuple[object, object, object]] = []

    def reason(
        self,
        problem: object,
        reasoning_type: object = None,
        context: object = None,
    ) -> dict[str, object]:
        self.calls.append((problem, reasoning_type, context))
        return {
            "result": "Evidence is mixed; uncertainty remains.",
            "confidence": 0.7,
        }

    def runtime_status(self) -> dict[str, str]:
        return {"health": "healthy"}


class FakeFactory:
    def __init__(self, agent: FakeAgent) -> None:
        self.agent = agent
        self.calls: list[tuple[str, object]] = []
        self.released: list[str] = []

    def create(self, agent_type: str, shared_memory: object = None) -> FakeAgent:
        self.calls.append((agent_type, shared_memory))
        return self.agent

    def release(self, agent_type: str) -> bool:
        self.released.append(agent_type)
        return True

    def health_check(self) -> dict[str, object]:
        return {
            "status": "ok",
            "health": "healthy",
            "lifecycle": "active",
            "registered_agents": 21,
            "active_agents": 1,
            "private_runtime_details": "must not leave the adapter",
        }


class FailingFactory:
    def create(self, agent_type: str, shared_memory: object = None) -> object:
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
            request_id="client-42",
        )
    )
    assert result.status is ReasoningStatus.AVAILABLE
    assert result.interpretation == "Evidence is mixed; uncertainty remains."
    assert result.correlation_id is not None
    assert result.request_id == "client-42"
    assert factory.calls == [("reasoning", memory)]
    assert len(memory.writes) == 2
    request_key, request_payload, _ = memory.writes[0]
    result_key, _, _ = memory.writes[1]
    assert request_key.startswith("slaifi:reasoning:request:")
    assert result_key.startswith("slaifi:reasoning:result:")
    assert isinstance(request_payload, dict)
    assert request_payload["request_id"] == "client-42"
    context = agent.calls[0][2]
    assert context["authoritative_evidence"]["latest_return_rate"] == 0.05
    assert context["request_id"] == "client-42"
    assert "Do not alter" in context["instruction"]


def test_repeated_reasoning_generates_distinct_correlation_keys() -> None:
    memory = FakeMemory()
    adapter = SlaiFinancialReasoner(
        factory=FakeFactory(FakeAgent()),
        shared_memory=memory,
    )
    first = adapter.reason(
        ReasoningRequest(operation="test", evidence={}, objective="interpret")
    )
    second = adapter.reason(
        ReasoningRequest(operation="test", evidence={}, objective="interpret")
    )
    assert first.correlation_id
    assert second.correlation_id
    assert first.correlation_id != second.correlation_id
    assert first.memory_key != second.memory_key


def test_optional_slai_runtime_degrades_without_breaking_financial_layer() -> None:
    adapter = SlaiFinancialReasoner(
        factory=FailingFactory(),
        shared_memory=FakeMemory(),
    )
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
        adapter.reason(
            ReasoningRequest(operation="test", evidence={}, objective="interpret")
        )


def test_partial_host_runtime_injection_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="must be supplied together"):
        SlaiFinancialReasoner(factory=FakeFactory(FakeAgent()))


def test_host_owned_runtime_is_never_closed_by_slaifi() -> None:
    memory = FakeMemory()
    factory = FakeFactory(FakeAgent())
    adapter = SlaiFinancialReasoner(factory=factory, shared_memory=memory)
    adapter.status()
    adapter.close()
    assert factory.released == []
    assert memory.closed is False


def test_lazily_created_runtime_is_released_and_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory = FakeMemory()
    factory = FakeFactory(FakeAgent())

    def fake_import(name: str) -> object:
        if name == "src.agents.agent_factory":
            return SimpleNamespace(AgentFactory=lambda: factory)
        if name == "src.agents.collaborative.shared_memory":
            return SimpleNamespace(SharedMemory=lambda: memory)
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(reasoner_module.importlib, "import_module", fake_import)

    adapter = SlaiFinancialReasoner()
    status = adapter.status()
    assert status.status is ReasoningStatus.AVAILABLE

    adapter.close()
    assert factory.released == ["reasoning"]
    assert memory.closed is True
