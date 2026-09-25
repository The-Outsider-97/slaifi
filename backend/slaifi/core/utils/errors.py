"""Cross-cutting SLAIFI exception categories.

Core owns only failure categories that higher layers may safely depend on. Domain
and Engine specializations live in their respective utility packages.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class SlaifiError(Exception):
    """Base class for expected SLAIFI failures with structured context."""

    def __init__(
        self,
        message: str,
        *,
        component: str | None = None,
        operation: str | None = None,
        cause: BaseException | None = None,
        context: Mapping[str, Any] | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.component = component
        self.operation = operation
        self.cause = cause
        self.context = dict(context or {})
        self.retryable = retryable

    def as_dict(self) -> dict[str, Any]:
        """Return stable diagnostic metadata without imposing logging or HTTP policy."""

        payload: dict[str, Any] = {
            "error_type": type(self).__name__,
            "message": self.message,
        }
        if self.component is not None:
            payload["component"] = self.component
        if self.operation is not None:
            payload["operation"] = self.operation
        if self.context:
            payload["context"] = dict(self.context)
        if self.retryable is not None:
            payload["retryable"] = self.retryable
        if self.cause is not None:
            payload["cause_type"] = type(self.cause).__name__
        return payload


class ConfigurationError(SlaifiError):
    """Runtime configuration is invalid or incomplete."""


class ValidationError(SlaifiError, ValueError):
    """An input or invariant violates an explicit SLAIFI contract."""


class CalculationError(SlaifiError, ArithmeticError):
    """A calculation is undefined or cannot be completed as requested."""


class IntegrationError(SlaifiError):
    """An external runtime integration failed or is unavailable."""


class InfrastructureError(SlaifiError):
    """An infrastructure adapter failed outside the financial domain model."""
