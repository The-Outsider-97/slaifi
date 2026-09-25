"""Small finance-agnostic primitives used across lower SLAIFI layers."""

from math import isfinite

from slaifi.core.exceptions import ValidationError


class CurrencyCode(str):
    """Validated ISO-like three-letter currency code.

    SLAIFI uses three-letter uppercase codes internally. This does not claim that
    every supported asset necessarily settles in an ISO-4217 currency; it simply
    establishes an unambiguous normalized identifier at monetary boundaries.
    """

    def __new__(cls, value: str) -> "CurrencyCode":
        normalized = value.strip().upper()
        if len(normalized) != 3 or not normalized.isalpha():
            raise ValidationError("currency code must contain exactly three letters")
        return str.__new__(cls, normalized)


def validate_rate(value: float, *, name: str = "rate") -> float:
    """Validate a finite fractional rate and return it unchanged.

    Rates use decimal fractions: ``0.10`` means ten percent.
    """

    if not isfinite(value):
        raise ValidationError(f"{name} must be finite")
    return value


def percent_to_rate(percent: float) -> float:
    """Convert a human percentage value to SLAIFI's fractional-rate convention."""

    if not isfinite(percent):
        raise ValidationError("percent must be finite")
    return percent / 100.0


def rate_to_percent(rate: float) -> float:
    """Convert an internal fractional rate to a human percentage value."""

    return validate_rate(rate) * 100.0
