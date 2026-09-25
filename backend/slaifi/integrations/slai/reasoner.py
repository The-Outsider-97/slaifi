"""Adapter from SLAIFI's reasoning port to the wider SLAI agent runtime."""

from __future__ import annotations

import importlib
import json
import uuid
from collections.abc import Mapping
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
        envelope = {
            "schema_version": 1,
            "source": "slaifi",
            "operation": request.operation,
            "objective": request.objective,
            "evidence": to_json_safe(request.evidence),
            "constraints": to_json_safe(request.constraints),
            "assumptions": to_json_safe(request.assumptions),
            "uncertainty": to_json_safe(request.uncertainty),
            "correlation_id": correlation_id,
            "request_id": request.request_id,
        }
        self._memory_set(request_key, envelope)

        context = {
            "application": "slaifi",
            "operation": request.operation,
            "authoritative_evidence": envelope["evidence"],
            "constraints": envelope["constraints"],
            "assumptions": envelope["assumptions"],
            "uncertainty": envelope["uncertainty"],
            "correlation_id": correlation_id,
            "request_id": request.request_id,
            "instruction": (
                "Interpret the supplied SLAIFI evidence. Do not alter, replace, or "
                "recalculate authoritative numerical evidence. Separate observed or "
                "calculated facts from qualitative interpretation and explicitly note "
                "uncertainty and conflicting evidence. Do not imply guaranteed returns."
            ),
        }
        try:
            raw = self._agent.reason(
                request.objective,
                reasoning_type=self._reasoning_type,
                context=context,
            )
            normalized = _mapping_result(raw)
            self._memory_set(result_key, normalized)
            return ReasoningResult(
                status=self._runtime_status(),
                interpretation=_extract_interpretation(normalized),
                raw_result=normalized,
                agent=self._agent_type,
                agent_version=_agent_version(self._agent),
                memory_key=result_key,
                correlation_id=correlation_id,
                request_id=request.request_id,
            )
        except Exception as exc:
            logger.exception("SLAI reasoning failed during %s", request.operation)
            if self._required:
                raise ReasoningUnavailableError(
                    f"SLAI reasoning failed: {type(exc).__name__}: {exc}"
                ) from exc
            return ReasoningResult(
                status=ReasoningStatus.DEGRADED,
                interpretation=None,
                agent=self._agent_type,
                agent_version=_agent_version(self._agent),
                correlation_id=correlation_id,
                request_id=request.request_id,
                warnings=(f"SLAI reasoning failed: {type(exc).__name__}: {exc}",),
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
        except TypeError:
            self._shared_memory.set(key, value)
        except Exception as exc:
            logger.warning("SLAI shared-memory write failed: %s", exc)

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
    return None


def _mapping_result(value: Any) -> dict[str, Any]:
    safe = to_json_safe(value)
    if isinstance(safe, dict):
        return safe
    return {"result": safe}


def _extract_interpretation(result: Mapping[str, Any]) -> str | None:
    for key in ("result", "output", "conclusion", "best_explanation", "response"):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if result:
        return json.dumps(result, ensure_ascii=False, sort_keys=True, default=str)
    return None
