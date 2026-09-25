"""Normalized market-domain value objects."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class AssetClass(StrEnum):
    """Asset classes supported by the normalized market boundary."""

    UNKNOWN = "unknown"
    EQUITY = "equity"
    ETF = "etf"
    INDEX = "index"
    BOND = "bond"
    COMMODITY = "commodity"
    FOREX = "forex"
    CRYPTO = "crypto"


@dataclass(frozen=True, slots=True)
class AssetRef:
    """Provider-neutral identity for a tradable or observable asset."""

    symbol: str
    asset_class: AssetClass = AssetClass.UNKNOWN
    exchange: str | None = None

    def __post_init__(self) -> None:
        normalized_symbol = self.symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("asset symbol must not be empty")
        object.__setattr__(self, "symbol", normalized_symbol)


@dataclass(frozen=True, slots=True)
class PriceQuote:
    """Normalized point-in-time market quote."""

    asset: AssetRef
    price: Decimal
    currency: str
    observed_at: datetime
    source: str
    change_percent: Decimal | None = None

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValueError("price must be positive")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        normalized_currency = self.currency.strip().upper()
        if len(normalized_currency) != 3:
            raise ValueError("currency must be a three-letter code")
        if not self.source.strip():
            raise ValueError("source must not be empty")
        object.__setattr__(self, "currency", normalized_currency)
