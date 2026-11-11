"""Compatibility imports for Core-owned SLAIFI errors.

New code should import from ``slaifi.core.utils.errors``. This module contains no
error definitions and intentionally does not re-export Domain or Engine errors.
"""

from slaifi.core.utils.errors import (
    CalculationError,
    ConfigurationError,
    ConflictError,
    InfrastructureError,
    IntegrationError,
    MarketDataError,
    MarketDataRateLimitedError,
    MarketDataUnavailableError,
    NotFoundError,
    SlaifiError,
    SymbolNotFoundError,
    ValidationError,
)

__all__ = [
    "CalculationError",
    "ConfigurationError",
    "ConflictError",
    "InfrastructureError",
    "IntegrationError",
    "MarketDataError",
    "MarketDataRateLimitedError",
    "MarketDataUnavailableError",
    "NotFoundError",
    "SlaifiError",
    "SymbolNotFoundError",
    "ValidationError",
]
