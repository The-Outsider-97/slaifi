"""Adapter from SLAIFI's reasoning port to the wider SLAI agent runtime."""

from __future__ import annotations

import importlib
import json
import logging
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from slaifi.application.contracts import (
    ReasoningRequest,
    ReasoningResult,
    ReasoningStatus,
    ReasoningUnavailableError,
)

logger = logging.getLogger(__name__)


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
        self._enabled = enabled
        self._required = required
        self._agent_type = agent_type
        self._reasoning_type = reasoning_type
        self._memory_ttl_seconds = memory_ttl_seconds
        self._factory = factory
        self._shared_memory = shared_memory
        self._agent: Any = None
        self._initialization_error: str | None = None

    def reason(self, request: ReasoningRequest) -> ReasoningResult:
        if not self._enabled:
            return ReasoningResult(
                status=ReasoningStatus.DISABLED,
                interpretation=None,
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
            "evidence": _json_safe(request.evidence),
            "constraints": _json_safe(request.constraints),
            "assumptions": _json_safe(request.assumptions),
            "uncertainty": _json_safe(request.uncertainty),
            "correlation_id": correlation_id,
        }
        self._memory_set(request_key, envelope)

        context = {
            "application": "slaifi",
            "operation": request.operation,
            "authoritative_evidence": envelope["evidence"],
            "constraints": envelope["constraints"],
            "assumptions": envelope["assumptions"],
            "uncertainty": envelope["uncertainty"],
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
            )
        except Exception as exc:
            logger.exception(
                "SLAI reasoning failed",
                extra={"component": "slai", "operation": request.operation},
            )
            if self._required:
                raise ReasoningUnavailableError(
                    f"SLAI reasoning failed: {type(exc).__name__}: {exc}"
                ) from exc
            return ReasoningResult(
                status=ReasoningStatus.DEGRADED,
                interpretation=None,
                agent=self._agent_type,
                agent_version=_agent_version(self._agent),
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
            raw_result=_runtime_payload(self._agent),
        )

    def _ensure_runtime(self) -> bool:
        if self._agent is not None:
            return True
        try:
            if self._factory is None:
                factory_module = importlib.import_module("src.agents.agent_factory")
                self._factory = factory_module.AgentFactory()
            if self._shared_memory is None:
                memory_module = importlib.import_module(
                    "src.agents.collaborative.shared_memory"
                )
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
            logger.warning(
                self._initialization_error,
                extra={"component": "slai", "operation": "initialize"},
            )
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
            logger.warning(
                "SLAI shared-memory write failed: %s",
                exc,
                extra={"component": "slai", "operation": "shared_memory_set"},
            )

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
    safe = _json_safe(value)
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


def _json_safe(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, (datetime, Decimal)):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
