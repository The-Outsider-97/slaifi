"""Provider-neutral asset identity."""

from dataclasses import dataclass
from enum import StrEnum

from slaifi.core.types import CurrencyCode
from slaifi.domain.utils import normalize_identifier


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
        object.__setattr__(
            self,
            "symbol",
            normalize_identifier(self.symbol, name="asset symbol", uppercase=True),
        )
        if self.exchange is not None:
            object.__setattr__(
                self,
                "exchange",
                normalize_identifier(self.exchange, name="exchange", uppercase=True),
            )
        if self.currency is not None and not isinstance(self.currency, CurrencyCode):
            object.__setattr__(self, "currency", CurrencyCode(str(self.currency)))
        if self.instrument_id is not None:
            object.__setattr__(
                self,
                "instrument_id",
                normalize_identifier(self.instrument_id, name="instrument_id"),
            )

    @property
    def display_symbol(self) -> str:
        return f"{self.exchange}:{self.symbol}" if self.exchange else self.symbol
