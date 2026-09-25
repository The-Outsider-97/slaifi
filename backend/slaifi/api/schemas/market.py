"""HTTP response schemas for market data."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from slaifi.application.market.get_overview import MarketOverview
from slaifi.domain.market.models import PriceQuote


class MarketQuoteResponse(BaseModel):
    """Serializable normalized quote; change_percent is a presentation value."""

    model_config = ConfigDict(frozen=True)
    symbol: str
    asset_class: str
    price: Decimal
    currency: str
    change_percent: Decimal | None
    observed_at: datetime
    source: str

    @classmethod
    def from_domain(cls, quote: PriceQuote) -> "MarketQuoteResponse":
        change_percent = None if quote.change_rate is None else Decimal(str(quote.change_rate * 100.0))
        return cls(symbol=quote.asset.symbol, asset_class=quote.asset.asset_class.value, price=quote.price, currency=quote.currency, change_percent=change_percent, observed_at=quote.observed_at, source=quote.source)


class MarketOverviewResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    generated_at: datetime
    quotes: list[MarketQuoteResponse]
    data_mode: str = "mock"

    @classmethod
    def from_domain(cls, overview: MarketOverview) -> "MarketOverviewResponse":
        return cls(generated_at=overview.generated_at, quotes=[MarketQuoteResponse.from_domain(quote) for quote in overview.quotes])
