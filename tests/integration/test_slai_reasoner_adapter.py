from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
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

    def __init__(self, *, degraded: bool = False) -> None:
        self.calls: list[tuple[object, object, object]] = []
        self.degraded = degraded

    def reason(
        self,
        problem: object,
        reasoning_type: object = None,
        context: object = None,
    ) -> dict[str, object]:
        self.calls.append((problem, reasoning_type, context))
        return {
            "schema": "slai.reasoning.result.v1",
            "conclusion": "Evidence is mixed; uncertainty remains.",
            "result": "Evidence is mixed; uncertainty remains.",
            "confidence": {"value": 0.7, "type": "heuristic", "calibrated": False},
            "outcome": "supported",
            "degraded": self.degraded,
            "validation": {"validation_status": "partial" if self.degraded else "passed"},
            "selection": {"resolved": "cause_effect", "method": "keyword_policy"},
            "contradictions": ["signal conflict"] if self.degraded else [],
        }

    def runtime_status(self) -> dict[str, str]:
        return {"health": "healthy"}


class FailingAgent(FakeAgent):
    def reason(self, problem: object, reasoning_type: object = None, context: object = None) -> dict[str, object]:
        raise RuntimeError("reasoning exploded")


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


class EvidenceKind(StrEnum):
    OBSERVED = "observed"


@dataclass(frozen=True)
class EvidenceRecord:
    timestamp: datetime
    amount: Decimal
    kind: EvidenceKind


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
    assert result.reasoning_strategy == "cause_effect"
    assert result.confidence == pytest.approx(0.7)
    assert result.outcome == "supported"
    assert result.validation_status == "passed"
    assert result.correlation_id is not None
    assert result.request_id == "client-42"
    assert factory.calls == [("reasoning", memory)]
    assert len(memory.writes) == 2
    request_key, request_payload, request_kwargs = memory.writes[0]
    result_key, result_payload, result_kwargs = memory.writes[1]
    assert request_key.startswith("slaifi:reasoning:request:")
    assert result_key.startswith("slaifi:reasoning:result:")
    assert isinstance(request_payload, dict)
    assert request_payload["schema_version"] == 2
    assert request_payload["request_id"] == "client-42"
    assert request_payload["correlation_id"] == result.correlation_id
    assert request_payload["agent"]["type"] == "reasoning"
    assert request_kwargs["tags"] == ["slaifi", "financial_reasoning"]
    assert isinstance(result_payload, dict)
    assert result_payload["schema_version"] == 2
    assert result_payload["reasoning"]["strategy"] == "cause_effect"
    assert result_payload["status"] == "available"
    assert result_kwargs["ttl"] == 900
    context = agent.calls[0][2]
    assert context["authoritative_evidence"]["latest_return_rate"] == 0.05
    assert context["evidence"]["latest_return_rate"] == 0.05
    assert context["request_id"] == "client-42"
    assert context["evidence_authority"] == "slaifi_domain_and_engines"
    assert "Risk considerations" in context["reasoning_framework"]
    assert context["guardrails"]["may_recalculate_authoritative_values"] is False


def test_repeated_reasoning_generates_distinct_correlation_keys() -> None:
    memory = FakeMemory()
    adapter = SlaiFinancialReasoner(
        factory=FakeFactory(FakeAgent()),
        shared_memory=memory,
    )
    first = adapter.reason(ReasoningRequest(operation="test", evidence={}, objective="interpret"))
    second = adapter.reason(ReasoningRequest(operation="test", evidence={}, objective="interpret"))
    assert first.correlation_id
    assert second.correlation_id
    assert first.correlation_id != second.correlation_id
    assert first.memory_key != second.memory_key


def test_json_safe_evidence_is_written_without_mutating_authoritative_input() -> None:
    memory = FakeMemory()
    adapter = SlaiFinancialReasoner(factory=FakeFactory(FakeAgent()), shared_memory=memory)
    record = EvidenceRecord(datetime(2026, 9, 25, tzinfo=UTC), Decimal("12.50"), EvidenceKind.OBSERVED)
    adapter.reason(ReasoningRequest(operation="test", evidence={"record": record}, objective="interpret"))
    request_payload = memory.writes[0][1]
    assert isinstance(request_payload, dict)
    assert request_payload["authoritative_evidence"]["record"]["amount"] == "12.50"
    assert request_payload["authoritative_evidence"]["record"]["kind"] == "observed"
    assert record.amount == Decimal("12.50")


def test_reasoning_level_degradation_is_exposed_even_when_agent_health_is_good() -> None:
    adapter = SlaiFinancialReasoner(factory=FakeFactory(FakeAgent(degraded=True)), shared_memory=FakeMemory())
    result = adapter.reason(ReasoningRequest(operation="test", evidence={}, objective="interpret"))
    assert result.status is ReasoningStatus.DEGRADED
    assert result.degraded is True
    assert result.validation_status == "partial"
    assert result.warnings


def test_optional_reasoning_failure_returns_degraded_result_and_audit_envelope() -> None:
    memory = FakeMemory()
    adapter = SlaiFinancialReasoner(factory=FakeFactory(FailingAgent()), shared_memory=memory)
    result = adapter.reason(ReasoningRequest(operation="test", evidence={}, objective="interpret"))
    assert result.status is ReasoningStatus.DEGRADED
    assert result.interpretation is None
    assert result.memory_key is not None
    assert len(memory.writes) == 2
    failed_payload = memory.writes[-1][1]
    assert isinstance(failed_payload, dict)
    assert failed_payload["status"] == "degraded"
    assert failed_payload["error_type"] == "RuntimeError"


def test_optional_slai_runtime_degrades_without_breaking_financial_layer() -> None:
    adapter = SlaiFinancialReasoner(factory=FailingFactory(), shared_memory=FakeMemory())
    result = adapter.reason(ReasoningRequest(operation="test", evidence={}, objective="interpret"))
    assert result.status is ReasoningStatus.UNAVAILABLE


def test_required_slai_runtime_fails_explicitly() -> None:
    adapter = SlaiFinancialReasoner(factory=FailingFactory(), shared_memory=FakeMemory(), required=True)
    with pytest.raises(ReasoningUnavailableError):
        adapter.reason(ReasoningRequest(operation="test", evidence={}, objective="interpret"))


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


def test_lazily_created_runtime_is_released_and_closed(monkeypatch: pytest.MonkeyPatch) -> None:
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
