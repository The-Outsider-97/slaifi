"""Domain-owned errors for financial invariants and business rules."""

from slaifi.core.utils.errors import SlaifiError, ValidationError


class DomainError(SlaifiError):
    """Base class for expected financial-domain failures."""


class DomainValidationError(DomainError, ValidationError):
    """A financial-domain object or invariant is invalid."""


class UnsupportedAssetError(DomainError):
    """A domain operation is not defined for the supplied asset type."""
