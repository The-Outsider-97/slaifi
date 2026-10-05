"""HTTP response schemas for normalized market data."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from slaifi.application.market import MarketHistory
from slaifi.application.market.get_overview import MarketOverview
from slaifi.domain.market.models import OHLCVBar, PriceQuote


class MarketQuoteResponse(BaseModel):
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
        change_percent = (
            None
            if quote.change_rate is None
            else Decimal(str(quote.change_rate * 100.0))
        )

        return cls(
            symbol=quote.asset.symbol,
            asset_class=quote.asset.asset_class.value,
            price=quote.price,
            currency=str(quote.currency),
            change_percent=change_percent,
            observed_at=quote.observed_at,
            source=quote.source,
        )


class MarketOverviewResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    generated_at: datetime
    quotes: list[MarketQuoteResponse]
    data_mode: str

    @classmethod
    def from_domain(cls, overview: MarketOverview) -> "MarketOverviewResponse":
        return cls(
            generated_at=overview.generated_at,
            quotes=[MarketQuoteResponse.from_domain(quote) for quote in overview.quotes],
            data_mode=overview.data_mode,
        )


class MarketBarResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    start_at: datetime
    end_at: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    @classmethod
    def from_domain(cls, bar: OHLCVBar) -> "MarketBarResponse":
        return cls(
            start_at=bar.start_at,
            end_at=bar.end_at,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
        )


class MarketHistoryResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    asset_class: str
    interval: str
    generated_at: datetime
    data_mode: str
    bars: list[MarketBarResponse]

    @classmethod
    def from_domain(cls, history: MarketHistory) -> "MarketHistoryResponse":
        return cls(
            symbol=history.asset.symbol,
            asset_class=history.asset.asset_class.value,
            interval=history.interval,
            generated_at=history.generated_at,
            data_mode=history.data_mode,
            bars=[MarketBarResponse.from_domain(bar) for bar in history.bars],
        )
