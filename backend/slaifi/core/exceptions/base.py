"""Small exception hierarchy shared by SLAIFI's lower layers."""


class SlaifiError(Exception):
    """Base class for expected SLAIFI failures."""


class ConfigurationError(SlaifiError):
    """Runtime configuration is invalid or incomplete."""


class ValidationError(SlaifiError, ValueError):
    """A domain or financial input violates an explicit invariant."""


class FinancialCalculationError(SlaifiError, ArithmeticError):
    """A financial result is mathematically undefined or cannot be calculated."""


class InsufficientDataError(FinancialCalculationError):
    """A calculation has fewer observations than its documented minimum."""


class UnsupportedAssetError(SlaifiError):
    """A requested operation is not defined for the supplied asset type."""
