"""SLAIFI exception hierarchy."""

from slaifi.core.exceptions.base import (
    ConfigurationError,
    FinancialCalculationError,
    InsufficientDataError,
    SlaifiError,
    UnsupportedAssetError,
    ValidationError,
)

__all__ = [
    "ConfigurationError",
    "FinancialCalculationError",
    "InsufficientDataError",
    "SlaifiError",
    "UnsupportedAssetError",
    "ValidationError",
]
