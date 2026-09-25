"""Normalized market observations independent of data providers."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from math import isfinite

from slaifi.core.exceptions import ValidationError
from slaifi.core.types import CurrencyCode
from slaifi.domain.assets import AssetClass, AssetId

AssetRef = AssetId


def _require_aware(timestamp: datetime, field_name: str) -> None:
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValidationError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class PriceQuote:
    """Normalized point-in-time quote. change_rate uses 0.05 for 5%."""

    asset: AssetId
    price: Decimal
    currency: CurrencyCode
    observed_at: datetime
    source: str
    change_rate: float | None = None

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValidationError("price must be positive")
        _require_aware(self.observed_at, "observed_at")
        if not isinstance(self.currency, CurrencyCode):
            object.__setattr__(self, "currency", CurrencyCode(str(self.currency)))
        source = self.source.strip()
        if not source:
            raise ValidationError("source must not be empty")
        object.__setattr__(self, "source", source)
        if self.change_rate is not None and not isfinite(self.change_rate):
            raise ValidationError("change_rate must be finite when supplied")


@dataclass(frozen=True, slots=True)
class OHLCVBar:
    asset: AssetId
    start_at: datetime
    end_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        _require_aware(self.start_at, "start_at")
        _require_aware(self.end_at, "end_at")
        if self.end_at <= self.start_at:
            raise ValidationError("end_at must be later than start_at")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValidationError("OHLC prices must be positive")
        if self.volume < 0:
            raise ValidationError("volume must be non-negative")
        if self.high < self.low:
            raise ValidationError("high must be greater than or equal to low")
        if self.high < self.open or self.high < self.close:
            raise ValidationError("high must be at least open and close")
        if self.low > self.open or self.low > self.close:
            raise ValidationError("low must be at most open and close")


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    as_of: datetime
    quotes: tuple[PriceQuote, ...]

    def __post_init__(self) -> None:
        _require_aware(self.as_of, "as_of")
        seen: set[AssetId] = set()
        for quote in self.quotes:
            if quote.asset in seen:
                raise ValidationError(f"duplicate quote for {quote.asset.display_symbol}")
            if quote.observed_at > self.as_of:
                raise ValidationError("snapshot cannot contain a quote from the future")
            seen.add(quote.asset)


__all__ = ["AssetClass", "AssetId", "AssetRef", "MarketSnapshot", "OHLCVBar", "PriceQuote"]
