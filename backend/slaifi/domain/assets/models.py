"""Provider-neutral asset identity."""

from dataclasses import dataclass
from enum import StrEnum

from slaifi.core.exceptions import ValidationError
from slaifi.core.types import CurrencyCode


class AssetClass(StrEnum):
    """Broad asset classes supported by the SLAIFI domain vocabulary."""

    UNKNOWN = "unknown"
    EQUITY = "equity"
    ETF = "etf"
    INDEX = "index"
    BOND = "bond"
    COMMODITY = "commodity"
    FOREX = "forex"
    CRYPTO = "crypto"


@dataclass(frozen=True, slots=True)
class AssetId:
    """Provider-neutral asset identity; symbol alone is not globally unique."""

    symbol: str
    asset_class: AssetClass = AssetClass.UNKNOWN
    exchange: str | None = None
    currency: CurrencyCode | None = None
    instrument_id: str | None = None

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper()
        if not symbol:
            raise ValidationError("asset symbol must not be empty")
        object.__setattr__(self, "symbol", symbol)
        if self.exchange is not None:
            exchange = self.exchange.strip().upper()
            if not exchange:
                raise ValidationError("exchange must not be blank when supplied")
            object.__setattr__(self, "exchange", exchange)
        if self.currency is not None and not isinstance(self.currency, CurrencyCode):
            object.__setattr__(self, "currency", CurrencyCode(str(self.currency)))
        if self.instrument_id is not None:
            instrument_id = self.instrument_id.strip()
            if not instrument_id:
                raise ValidationError("instrument_id must not be blank when supplied")
            object.__setattr__(self, "instrument_id", instrument_id)

    @property
    def display_symbol(self) -> str:
        return f"{self.exchange}:{self.symbol}" if self.exchange else self.symbol
