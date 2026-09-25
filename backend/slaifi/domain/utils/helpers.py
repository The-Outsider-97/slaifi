"""Reusable financial-domain validation and normalization helpers."""

from datetime import datetime

from slaifi.core.utils.helpers import is_aware_datetime
from slaifi.domain.utils.errors import DomainValidationError


def require_aware_datetime(value: datetime, *, name: str) -> datetime:
    """Require a timezone-aware domain timestamp and return it unchanged."""

    if not is_aware_datetime(value):
        raise DomainValidationError(f"{name} must be timezone-aware")
    return value


def require_non_blank(value: str, *, name: str) -> str:
    """Require non-blank text while preserving the caller's original value."""

    if not value.strip():
        raise DomainValidationError(f"{name} must not be empty")
    return value


def normalize_identifier(
    value: str,
    *,
    name: str,
    uppercase: bool = False,
) -> str:
    """Strip and optionally uppercase a domain identifier."""

    normalized = value.strip()
    if not normalized:
        raise DomainValidationError(f"{name} must not be empty")
    return normalized.upper() if uppercase else normalized
