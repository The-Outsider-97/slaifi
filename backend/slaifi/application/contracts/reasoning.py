"""SLAIFI-owned contract for contextual financial reasoning."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Protocol

from slaifi.core.exceptions import SlaifiError


class ReasoningUnavailableError(SlaifiError):
    """Configured contextual reasoning is required but currently unavailable."""


class ReasoningStatus(StrEnum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class ReasoningRequest:
    """Immutable evidence envelope supplied to a contextual reasoner."""

    operation: str
    evidence: Mapping[str, Any]
    objective: str
    constraints: Mapping[str, Any] = field(default_factory=dict)
    assumptions: Mapping[str, Any] = field(default_factory=dict)
    uncertainty: Mapping[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class ReasoningResult:
    """Contextual interpretation kept distinct from authoritative calculations."""

    status: ReasoningStatus
    interpretation: str | None
    raw_result: Mapping[str, Any] = field(default_factory=dict)
    agent: str | None = None
    agent_version: str | None = None
    memory_key: str | None = None
    correlation_id: str | None = None
    request_id: str | None = None
    warnings: tuple[str, ...] = ()


class FinancialReasoner(Protocol):
    """Port used by application services for optional contextual reasoning."""

    def reason(self, request: ReasoningRequest) -> ReasoningResult:
        """Interpret already-calculated financial evidence."""
        ...

    def status(self) -> ReasoningResult:
        """Report integration availability without performing financial analysis."""
        ...
