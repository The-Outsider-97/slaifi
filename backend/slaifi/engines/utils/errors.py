"""Engine-owned numerical and calculation errors."""

from slaifi.core.utils.errors import CalculationError, SlaifiError, ValidationError


class EngineError(SlaifiError):
    """Base class for expected quantitative-engine failures."""


class EngineValidationError(EngineError, ValidationError):
    """A numerical input or calculation parameter is invalid."""


class FinancialCalculationError(EngineError, CalculationError):
    """A financial result is mathematically undefined or cannot be calculated."""


class InsufficientDataError(FinancialCalculationError):
    """A calculation has fewer observations than its documented minimum."""
