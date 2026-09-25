"""Adapter from SLAIFI's reasoning port to the wider SLAI agent runtime."""

from __future__ import annotations

import importlib
import json
import math
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from logs.logger import get_logger

from slaifi.application.contracts import (
    ReasoningRequest,
    ReasoningResult,
    ReasoningStatus,
    ReasoningUnavailableError,
)
from slaifi.core.utils import ConfigurationError, to_json_safe

logger = get_logger("SLAIFI SLAI Integration")

_REASONING_FRAMEWORK = (
    "Market context",
    "Observed evidence",
    "Portfolio relevance",
    "Risk considerations",
    "Goal alignment",
    "Conflicting signals",
    "Uncertainty",
    "Conditions that could change the interpretation",
)


class SlaiFinancialReasoner:
    """Use SLAI AgentFactory + SharedMemory without coupling lower layers to SLAI."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        required: bool = False,
        agent_type: str = "reasoning",
        reasoning_type: str | None = None,
        memory_ttl_seconds: int = 900,
        factory: Any = None,
        shared_memory: Any = None,
    ) -> None:
        if (factory is None) != (shared_memory is None):
            raise ConfigurationError(
                "slai_factory and slai_shared_memory must be supplied together"
            )
        self._enabled = enabled
        self._required = required
        self._agent_type = agent_type
        self._reasoning_type = reasoning_type
        self._memory_ttl_seconds = memory_ttl_seconds
        self._factory = factory
        self._shared_memory = shared_memory
        self._owns_runtime = factory is None
        self._agent: Any = None
        self._initialization_error: str | None = None

    def reason(self, request: ReasoningRequest) -> ReasoningResult:
        if not self._enabled:
            return ReasoningResult(
                status=ReasoningStatus.DISABLED,
                interpretation=None,
                correlation_id=request.correlation_id,
                request_id=request.request_id,
                warnings=("SLAI integration is disabled by configuration.",),
            )
        if not self._ensure_runtime():
            if self._required:
                raise ReasoningUnavailableError(
                    self._initialization_error or "SLAI runtime unavailable"
                )
            return ReasoningResult(
                status=ReasoningStatus.UNAVAILABLE,
                interpretation=None,
                correlation_id=request.correlation_id,
                request_id=request.request_id,
                warnings=(self._initialization_error or "SLAI runtime unavailable",),
            )

        correlation_id = request.correlation_id or uuid.uuid4().hex
        request_key = f"slaifi:reasoning:request:{correlation_id}"
        result_key = f"slaifi:reasoning:result:{correlation_id}"
        evidence = to_json_safe(request.evidence)
        constraints = to_json_safe(request.constraints)
        assumptions = to_json_safe(request.assumptions)
        uncertainty = to_json_safe(request.uncertainty)
        started_at = datetime.now(UTC).isoformat()
        agent_version = _agent_version(self._agent)
        envelope = {
            "schema_version": 2,
            "source": "slaifi",
            "operation": request.operation,
            "objective": request.objective,
            "authoritative_evidence": evidence,
            "constraints": constraints,
            "assumptions": assumptions,
            "uncertainty": uncertainty,
            "request_id": request.request_id,
            "correlation_id": correlation_id,
            "created_at": started_at,
            "agent": {
                "type": self._agent_type,
                "version": agent_version,
                "reasoning_type": self._reasoning_type or "auto",
            },
        }
        self._memory_set(request_key, envelope)

        context = {
            "application": "slaifi",
            "operation": request.operation,
            "authoritative_evidence": evidence,
            "evidence": evidence,
            "constraints": constraints,
            "assumptions": assumptions,
            "uncertainty": uncertainty,
            "request_id": request.request_id,
            "correlation_id": correlation_id,
            "evidence_authority": "slaifi_domain_and_engines",
            "reasoning_framework": list(_REASONING_FRAMEWORK),
            "guardrails": {
                "engine_calculations_are_authoritative": True,
                "may_recalculate_authoritative_values": False,
                "may_fabricate_prices_or_holdings": False,
                "may_invent_confidence": False,
                "may_imply_guaranteed_returns": False,
                "may_convert_analysis_into_trade_instruction": False,
            },
            "instruction": (
                "Interpret the structured SLAIFI evidence without replacing or silently "
                "recalculating any authoritative figure. Separate observations from "
                "interpretation. When supported by the supplied evidence, organize the "
                "result around market context, observed evidence, portfolio relevance, "
                "risk, goal alignment, conflicting signals, uncertainty, and conditions "
                "that could change the interpretation. Do not fabricate missing prices, "
                "holdings, confidence, or goals; do not imply guaranteed returns or turn "
                "illustrative analysis into an execution instruction."
            ),
        }
        try:
            raw = self._agent.reason(
                request.objective,
                reasoning_type=self._reasoning_type,
                context=context,
            )
            normalized = _mapping_result(raw)
            metadata = _reasoning_metadata(normalized)
            status = self._result_status(normalized)
            warnings = _reasoning_warnings(normalized)
            interpretation = _extract_interpretation(normalized)
            result_envelope = {
                "schema_version": 2,
                "source": "slaifi",
                "operation": request.operation,
                "request_id": request.request_id,
                "correlation_id": correlation_id,
                "completed_at": datetime.now(UTC).isoformat(),
                "agent": {"type": self._agent_type, "version": agent_version},
                "status": status.value,
                "reasoning": metadata,
                "interpretation": interpretation,
                "warnings": list(warnings),
            }
            self._memory_set(result_key, result_envelope)
            return ReasoningResult(
                status=status,
                interpretation=interpretation,
                raw_result=normalized,
                agent=self._agent_type,
                agent_version=agent_version,
                memory_key=result_key,
                correlation_id=correlation_id,
                request_id=request.request_id,
                reasoning_strategy=metadata["strategy"],
                confidence=metadata["confidence"],
                outcome=metadata["outcome"],
                degraded=bool(metadata["degraded"]),
                validation_status=metadata["validation_status"],
                warnings=warnings,
            )
        except Exception as exc:
            logger.exception("SLAI reasoning failed during %s", request.operation)
            if self._required:
                raise ReasoningUnavailableError(
                    f"SLAI reasoning failed: {type(exc).__name__}: {exc}"
                ) from exc
            warning = f"SLAI reasoning failed: {type(exc).__name__}: {exc}"
            self._memory_set(
                result_key,
                {
                    "schema_version": 2,
                    "source": "slaifi",
                    "operation": request.operation,
                    "request_id": request.request_id,
                    "correlation_id": correlation_id,
                    "completed_at": datetime.now(UTC).isoformat(),
                    "agent": {"type": self._agent_type, "version": agent_version},
                    "status": ReasoningStatus.DEGRADED.value,
                    "error_type": type(exc).__name__,
                },
            )
            return ReasoningResult(
                status=ReasoningStatus.DEGRADED,
                interpretation=None,
                agent=self._agent_type,
                agent_version=agent_version,
                memory_key=result_key,
                correlation_id=correlation_id,
                request_id=request.request_id,
                degraded=True,
                warnings=(warning,),
            )

    def status(self) -> ReasoningResult:
        if not self._enabled:
            return ReasoningResult(status=ReasoningStatus.DISABLED, interpretation=None)
        if not self._ensure_runtime():
            return ReasoningResult(
                status=ReasoningStatus.UNAVAILABLE,
                interpretation=None,
                warnings=(self._initialization_error or "SLAI runtime unavailable",),
            )
        return ReasoningResult(
            status=self._runtime_status(),
            interpretation=None,
            agent=self._agent_type,
            agent_version=_agent_version(self._agent),
            raw_result=self._diagnostic_payload(),
        )

    def close(self) -> None:
        """Release only SLAI resources created and therefore owned by this adapter."""

        if self._owns_runtime and self._factory is not None:
            release = getattr(self._factory, "release", None)
            if callable(release):
                try:
                    release(self._agent_type)
                except Exception as exc:
                    logger.warning("Unable to release SLAI agent: %s", exc)
        if self._owns_runtime and self._shared_memory is not None:
            close = getattr(self._shared_memory, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as exc:
                    logger.warning("Unable to close SLAI shared memory: %s", exc)
        self._agent = None
        if self._owns_runtime:
            self._factory = None
            self._shared_memory = None

    def _ensure_runtime(self) -> bool:
        if self._agent is not None:
            return True
        try:
            if self._factory is None:
                factory_module = importlib.import_module("src.agents.agent_factory")
                self._factory = factory_module.AgentFactory()
            if self._shared_memory is None:
                memory_module = importlib.import_module("src.agents.collaborative.shared_memory")
                self._shared_memory = memory_module.SharedMemory()
            self._agent = self._factory.create(
                self._agent_type,
                shared_memory=self._shared_memory,
            )
            self._initialization_error = None
            return True
        except Exception as exc:
            self._initialization_error = (
                f"SLAI runtime unavailable: {type(exc).__name__}: {exc}"
            )
            logger.warning("%s", self._initialization_error)
            return False

    def _memory_set(self, key: str, value: Any) -> None:
        if self._shared_memory is None:
            return
        try:
            self._shared_memory.set(
                key,
                value,
                ttl=self._memory_ttl_seconds,
                tags=["slaifi", "financial_reasoning"],
            )
        except Exception as exc:
            logger.warning("SLAI shared-memory write failed: %s", exc)

    def _result_status(self, result: Mapping[str, Any]) -> ReasoningStatus:
        runtime = self._runtime_status()
        if runtime is ReasoningStatus.UNAVAILABLE:
            return runtime
        metadata = _reasoning_metadata(result)
        if bool(metadata["degraded"]) or metadata["validation_status"] in {
            "failed",
            "partial",
            "unavailable",
        }:
            return ReasoningStatus.DEGRADED
        return runtime

    def _runtime_status(self) -> ReasoningStatus:
        payload = _runtime_payload(self._agent)
        state = str(
            payload.get(
                "operational_state",
                payload.get("health", payload.get("status", "healthy")),
            )
        ).lower()
        if state in {"unavailable", "failed", "error", "stopped"}:
            return ReasoningStatus.UNAVAILABLE
        if state in {"degraded", "warning"}:
            return ReasoningStatus.DEGRADED
        return ReasoningStatus.AVAILABLE

    def _diagnostic_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"agent": _runtime_payload(self._agent)}
        health_check = getattr(self._factory, "health_check", None)
        if callable(health_check):
            try:
                factory_health = health_check()
            except Exception as exc:
                payload["factory"] = {
                    "status": "degraded",
                    "error_type": type(exc).__name__,
                }
            else:
                if isinstance(factory_health, Mapping):
                    payload["factory"] = {
                        "status": factory_health.get("status"),
                        "health": factory_health.get("health"),
                        "lifecycle": factory_health.get("lifecycle"),
                        "registered_agents": factory_health.get("registered_agents"),
                        "active_agents": factory_health.get("active_agents"),
                    }
        memory_health = getattr(self._shared_memory, "health_check", None)
        if callable(memory_health):
            try:
                value = memory_health()
            except Exception as exc:
                payload["shared_memory"] = {
                    "status": "degraded",
                    "error_type": type(exc).__name__,
                }
            else:
                if isinstance(value, Mapping):
                    payload["shared_memory"] = {
                        key: value.get(key)
                        for key in ("status", "health", "item_count", "closed")
                        if key in value
                    }
        return payload


def _runtime_payload(agent: Any) -> dict[str, Any]:
    method = getattr(agent, "runtime_status", None)
    if not callable(method):
        return {}
    try:
        value = method()
    except Exception:
        return {}
    return dict(value) if isinstance(value, Mapping) else {"status": str(value)}


def _agent_version(agent: Any) -> str | None:
    for name in ("version", "__version__"):
        value = getattr(agent, name, None)
        if value is not None:
            return str(value)
    module_name = getattr(type(agent), "__module__", None)
    if isinstance(module_name, str) and module_name:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            return None
        value = getattr(module, "__version__", None)
        return str(value) if value is not None else None
    return None


def _mapping_result(value: Any) -> dict[str, Any]:
    safe = to_json_safe(value)
    if isinstance(safe, dict):
        return safe
    return {"result": safe}


def _extract_interpretation(result: Mapping[str, Any]) -> str | None:
    for key in ("conclusion", "result", "response", "best_explanation", "output"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if result:
        return json.dumps(result, ensure_ascii=False, sort_keys=True, default=str)
    return None


def _reasoning_metadata(result: Mapping[str, Any]) -> dict[str, Any]:
    selection = result.get("selection")
    selection_mapping = selection if isinstance(selection, Mapping) else {}
    strategy_value = selection_mapping.get("resolved") or result.get("reasoning_type") or result.get("strategy")
    confidence_value: float | None = None
    confidence = result.get("confidence")
    if isinstance(confidence, Mapping):
        raw_confidence = confidence.get("value")
    else:
        raw_confidence = confidence
    if isinstance(raw_confidence, (int, float)) and not isinstance(raw_confidence, bool):
        candidate = float(raw_confidence)
        if math.isfinite(candidate):
            confidence_value = candidate
    validation = result.get("validation")
    validation_mapping = validation if isinstance(validation, Mapping) else {}
    validation_value = validation_mapping.get("validation_status", validation_mapping.get("status"))
    return {
        "strategy": str(strategy_value) if strategy_value not in (None, "") else None,
        "confidence": confidence_value,
        "outcome": str(result["outcome"]) if result.get("outcome") not in (None, "") else None,
        "degraded": bool(result.get("degraded", False)),
        "validation_status": (
            str(validation_value).strip().lower()
            if validation_value not in (None, "")
            else None
        ),
        "stop_reason": str(result["stop_reason"]) if result.get("stop_reason") not in (None, "") else None,
    }


def _reasoning_warnings(result: Mapping[str, Any]) -> tuple[str, ...]:
    warnings: list[str] = []
    metadata = _reasoning_metadata(result)
    if metadata["degraded"]:
        warnings.append("SLAI reasoning reported degraded execution.")
    validation_status = metadata["validation_status"]
    if validation_status in {"failed", "partial", "unavailable"}:
        warnings.append(f"SLAI reasoning validation status: {validation_status}.")
    contradictions = result.get("contradictions")
    if isinstance(contradictions, Sequence) and not isinstance(contradictions, (str, bytes)):
        if contradictions:
            warnings.append(f"SLAI reasoning reported {len(contradictions)} conflicting signal(s).")
    fallback = result.get("fallback")
    if isinstance(fallback, Mapping) and bool(fallback.get("used", False)):
        warnings.append("SLAI reasoning used a fallback path.")
    return tuple(warnings)
