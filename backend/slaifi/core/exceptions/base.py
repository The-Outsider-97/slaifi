"""Base exceptions shared by SLAIFI boundaries."""


class SlaifiError(Exception):
    """Base class for expected SLAIFI application failures."""


class ConfigurationError(SlaifiError):
    """Raised when runtime configuration is invalid or incomplete."""
