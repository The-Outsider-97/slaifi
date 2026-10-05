"""Adapter from SLAIFI's reasoning port to the wider SLAI agent runtime."""

from __future__ import annotations

import importlib
import json
import math
import time
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
    """Use SLAI reasoning with bounded quality and safety review.

    SLAIFI remains authoritative for financial facts and calculations. SLAI receives
    structured evidence and may interpret it, but cannot replace deterministic values.
    Quality may trigger one refinement pass. Safety reviews only the final generated
    interpretation, never the authoritative financial evidence or private portfolio data.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        required: bool = False,
        agent_type: str = "reasoning",
        reasoning_type: str | None = None,
        quality_enabled: bool = False,
        quality_agent_type: str = "quality",
        refinement_enabled: bool = True,
        safety_enabled: bool = False,
        safety_agent_type: str = "safety",
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
        self._quality_enabled = quality_enabled
        self._quality_agent_type = quality_agent_type
        self._refinement_enabled = refinement_enabled
        self._safety_enabled = safety_enabled
        self._safety_agent_type = safety_agent_type
        self._memory_ttl_seconds = memory_ttl_seconds
        self._factory = factory
        self._shared_memory = shared_memory
        self._owns_runtime = factory is None
        self._agents: dict[str, Any] = {}
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
        started_at = time.perf_counter()
        started_iso = datetime.now(UTC).isoformat()
        reasoning_agent = self._agents[self._agent_type]
        agent_version = _agent_version(reasoning_agent)

        envelope = {
            "schema_version": 4,
            "source": "slaifi",
            "operation": request.operation,
            "objective": request.objective,
            "authoritative_evidence": evidence,
            "constraints": constraints,
            "assumptions": assumptions,
            "uncertainty": uncertainty,
            "request_id": request.request_id,
            "correlation_id": correlation_id,
            "created_at": started_iso,
            "agent": {
                "type": self._agent_type,
                "version": agent_version,
                "reasoning_type": self._reasoning_type or "auto",
            },
        }
        self._memory_set(request_key, envelope)

        context = self._reasoning_context(
            request=request,
            evidence=evidence,
            constraints=constraints,
            assumptions=assumptions,
            uncertainty=uncertainty,
            correlation_id=correlation_id,
        )

        try:
            normalized = self._invoke_reasoning(reasoning_agent, request.objective, context)
            quality_result = self._quality_gate(
                normalized=normalized,
                request=request,
                evidence=evidence,
                correlation_id=correlation_id,
            )

            if (
                self._refinement_enabled
                and quality_result is not None
                and _quality_verdict(quality_result) == "block"
            ):
                refinement_context = {
                    **context,
                    "prior_reasoning": normalized,
                    "quality_feedback": to_json_safe(quality_result),
                    "instruction": (
                        f"{context['instruction']} The previous interpretation failed the SLAI "
                        "quality gate. Refine it once using the quality findings, removing "
                        "unsupported or contradictory claims. Do not add new facts."
                    ),
                }
                normalized = self._invoke_reasoning(
                    reasoning_agent,
                    request.objective,
                    refinement_context,
                )
                quality_result = self._quality_gate(
                    normalized=normalized,
                    request=request,
                    evidence=evidence,
                    correlation_id=correlation_id,
                    refinement=True,
                )

            metadata = _reasoning_metadata(normalized)
            status = self._result_status(normalized)
            warnings = list(_reasoning_warnings(normalized))
            quality_status = None
            if quality_result is not None:
                quality_status = _quality_verdict(quality_result)
                if quality_status == "warn":
                    warnings.append("SLAI quality gate returned a warning verdict.")
                    if status is ReasoningStatus.AVAILABLE:
                        status = ReasoningStatus.DEGRADED
                elif quality_status == "block":
                    warnings.append("SLAI quality gate blocked the reasoning artifact.")
                    status = ReasoningStatus.DEGRADED

            interpretation = _extract_interpretation(normalized)
            if quality_status == "block":
                interpretation = None

            safety_result = self._safety_gate(
                interpretation=interpretation,
                operation=request.operation,
                correlation_id=correlation_id,
            )
            safety_status = _safety_verdict(safety_result) if safety_result is not None else None
            if safety_status == "review":
                warnings.append("SLAI safety gate requires review of the interpretation.")
                if status is ReasoningStatus.AVAILABLE:
                    status = ReasoningStatus.DEGRADED
            elif safety_status == "block":
                warnings.append("SLAI safety gate blocked the interpretation.")
                status = ReasoningStatus.DEGRADED
                interpretation = None

            duration_ms = max((time.perf_counter() - started_at) * 1000.0, 0.0)
            validation_status = _merged_validation_status(
                metadata.get("validation_status"), quality_status, safety_status
            )
            result_envelope = {
                "schema_version": 4,
                "source": "slaifi",
                "operation": request.operation,
                "request_id": request.request_id,
                "correlation_id": correlation_id,
                "completed_at": datetime.now(UTC).isoformat(),
                "duration_ms": duration_ms,
                "agent": {"type": self._agent_type, "version": agent_version},
                "quality_agent": self._quality_agent_type if quality_result is not None else None,
                "safety_agent": self._safety_agent_type if safety_result is not None else None,
                "status": status.value,
                "reasoning": metadata,
                "quality": to_json_safe(quality_result) if quality_result is not None else None,
                "safety": _public_safety_result(safety_result),
                "interpretation": interpretation,
                "warnings": warnings,
            }
            self._memory_set(result_key, result_envelope)
            logger.info(
                "SLAI analysis completed | operation=%s | status=%s | quality=%s | safety=%s | duration_ms=%.2f",
                request.operation,
                status.value,
                quality_status or "not_run",
                safety_status or "not_run",
                duration_ms,
            )
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
                degraded=status is ReasoningStatus.DEGRADED or bool(metadata["degraded"]),
                validation_status=validation_status,
                safety_status=safety_status,
                safety_agent=self._safety_agent_type if safety_result is not None else None,
                warnings=tuple(dict.fromkeys(warnings)),
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
                    "schema_version": 4,
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
        reasoning_agent = self._agents[self._agent_type]
        return ReasoningResult(
            status=self._runtime_status(reasoning_agent),
            interpretation=None,
            agent=self._agent_type,
            agent_version=_agent_version(reasoning_agent),
            raw_result=self._diagnostic_payload(),
        )

    def close(self) -> None:
        """Release only SLAI resources created and therefore owned by this adapter."""

        if self._owns_runtime and self._factory is not None:
            release = getattr(self._factory, "release", None)
            if callable(release):
                for agent_name in tuple(self._agents):
                    try:
                        release(agent_name)
                    except Exception as exc:
                        logger.warning("Unable to release SLAI agent %s: %s", agent_name, exc)
        if self._owns_runtime and self._shared_memory is not None:
            close = getattr(self._shared_memory, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as exc:
                    logger.warning("Unable to close SLAI shared memory: %s", exc)
        self._agents.clear()
        if self._owns_runtime:
            self._factory = None
            self._shared_memory = None

    def _ensure_runtime(self) -> bool:
        if self._agent_type in self._agents:
            return True
        try:
            if self._factory is None:
                factory_module = importlib.import_module("src.agents.agent_factory")
                self._factory = factory_module.AgentFactory()
            if self._shared_memory is None:
                memory_module = importlib.import_module("src.agents.collaborative.shared_memory")
                self._shared_memory = memory_module.SharedMemory()
            self._agents[self._agent_type] = self._factory.create(
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

    def _agent(self, name: str) -> Any:
        if name not in self._agents:
            if self._factory is None or self._shared_memory is None:
                raise ReasoningUnavailableError("SLAI runtime has not been initialized")
            self._agents[name] = self._factory.create(name, shared_memory=self._shared_memory)
        return self._agents[name]

    def _invoke_reasoning(
        self,
        agent: Any,
        objective: str,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        raw = agent.reason(
            objective,
            reasoning_type=self._reasoning_type,
            context=dict(context),
        )
        return _mapping_result(raw)

    def _quality_gate(
        self,
        *,
        normalized: Mapping[str, Any],
        request: ReasoningRequest,
        evidence: Any,
        correlation_id: str,
        refinement: bool = False,
    ) -> dict[str, Any] | None:
        if not self._quality_enabled:
            return None
        try:
            quality_agent = self._agent(self._quality_agent_type)
            interpretation = _extract_interpretation(normalized)
            record = {
                "operation": request.operation,
                "objective": request.objective,
                "interpretation": interpretation,
                "reasoning_strategy": _reasoning_metadata(normalized)["strategy"],
                "confidence": _reasoning_metadata(normalized)["confidence"],
                "has_authoritative_evidence": bool(evidence),
                "refinement": refinement,
            }
            result = quality_agent.perform_task(
                {
                    "operation": "evaluate_batch",
                    "records": [record],
                    "dataset_id": "slaifi_reasoning",
                    "source_id": "slaifi",
                    "batch_id": correlation_id,
                    "context": {
                        "purpose": "reasoning_artifact_quality_gate",
                        "financial_facts_are_authoritative": True,
                        "must_not_fabricate_missing_evidence": True,
                    },
                }
            )
            return dict(result) if isinstance(result, Mapping) else {"result": to_json_safe(result)}
        except Exception as exc:
            logger.warning("SLAI quality gate unavailable: %s", exc)
            return {
                "verdict": "warn",
                "flags": ["quality_agent_unavailable"],
                "error_type": type(exc).__name__,
            }

    def _safety_gate(
        self,
        *,
        interpretation: str | None,
        operation: str,
        correlation_id: str,
    ) -> dict[str, Any] | None:
        if not self._safety_enabled or not interpretation:
            return None
        try:
            safety_agent = self._agent(self._safety_agent_type)
            result = safety_agent.perform_task(
                {"text": interpretation},
                context={
                    "application": "slaifi",
                    "purpose": "financial_interpretation_review",
                    "operation": operation,
                    "correlation_id": correlation_id,
                    "financial_facts_included": False,
                    "user_portfolio_data_included": False,
                },
            )
            return dict(result) if isinstance(result, Mapping) else {"result": to_json_safe(result)}
        except Exception as exc:
            logger.warning("SLAI safety gate unavailable: %s", exc)
            return {
                "decision": "review",
                "warnings": ["safety_agent_unavailable"],
                "error_type": type(exc).__name__,
            }

    @staticmethod
    def _reasoning_context(
        *,
        request: ReasoningRequest,
        evidence: Any,
        constraints: Any,
        assumptions: Any,
        uncertainty: Any,
        correlation_id: str,
    ) -> dict[str, Any]:
        return {
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
                "recalculating any authoritative figure. Separate facts, derived metrics, "
                "and interpretation. Explicitly identify missing evidence and uncertainty. "
                "Do not fabricate prices, holdings, performance, confidence, or goals; do "
                "not imply guaranteed returns or convert analysis into a trade instruction."
            ),
        }

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
        runtime = self._runtime_status(self._agents[self._agent_type])
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

    @staticmethod
    def _runtime_status(agent: Any) -> ReasoningStatus:
        payload = _runtime_payload(agent)
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
        payload: dict[str, Any] = {
            "agents": {name: _runtime_payload(agent) for name, agent in self._agents.items()}
        }
        health_check = getattr(self._factory, "health_check", None)
        if callable(health_check):
            try:
                factory_health = health_check()
            except Exception as exc:
                payload["factory"] = {"status": "degraded", "error_type": type(exc).__name__}
            else:
                if isinstance(factory_health, Mapping):
                    payload["factory"] = {
                        key: factory_health.get(key)
                        for key in ("status", "health", "lifecycle", "registered_agents", "active_agents")
                        if key in factory_health
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
    strategy_value = (
        selection_mapping.get("resolved")
        or result.get("reasoning_type")
        or result.get("strategy")
    )
    confidence_value: float | None = None
    confidence = result.get("confidence")
    raw_confidence = confidence.get("value") if isinstance(confidence, Mapping) else confidence
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
            warnings.append(
                f"SLAI reasoning reported {len(contradictions)} conflicting signal(s)."
            )
    fallback = result.get("fallback")
    if isinstance(fallback, Mapping) and bool(fallback.get("used", False)):
        warnings.append("SLAI reasoning used a fallback path.")
    return tuple(warnings)


def _quality_verdict(result: Mapping[str, Any]) -> str:
    raw = result.get("quality_verdict", result.get("verdict", "warn"))
    normalized = str(raw).strip().lower()
    if normalized in {"pass", "warn", "block"}:
        return normalized
    return "warn"


def _safety_verdict(result: Mapping[str, Any]) -> str:
    raw = result.get("decision")
    normalized = str(raw).strip().lower() if raw not in (None, "") else ""
    if normalized in {"allow", "review", "block"}:
        return normalized
    is_safe = result.get("is_safe")
    if is_safe is True:
        return "allow"
    if is_safe is False:
        return "block"
    return "review"


def _public_safety_result(result: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if result is None:
        return None
    return {
        key: to_json_safe(result.get(key))
        for key in ("decision", "risk_level", "is_safe", "warnings", "blockers", "error_type")
        if key in result
    }


def _merged_validation_status(
    reasoning_status: Any,
    quality_verdict: str | None,
    safety_verdict: str | None = None,
) -> str | None:
    if quality_verdict == "block" or safety_verdict == "block":
        return "failed"
    if reasoning_status in {"failed", "unavailable"}:
        return str(reasoning_status)
    if quality_verdict == "warn" or safety_verdict == "review" or reasoning_status == "partial":
        return "partial"
    if quality_verdict == "pass":
        return "passed"
    return str(reasoning_status) if reasoning_status else None
