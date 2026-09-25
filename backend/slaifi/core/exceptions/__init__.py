"""Compatibility imports for Core-owned SLAIFI errors.

New code should import from ``slaifi.core.utils.errors``. This module contains no
error definitions and intentionally does not re-export Domain or Engine errors.
"""

from slaifi.core.utils.errors import (
    CalculationError,
    ConfigurationError,
    InfrastructureError,
    IntegrationError,
    SlaifiError,
    ValidationError,
)

__all__ = [
    "CalculationError",
    "ConfigurationError",
    "InfrastructureError",
    "IntegrationError",
    "SlaifiError",
    "ValidationError",
]
