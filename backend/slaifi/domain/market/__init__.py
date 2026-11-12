"""Normalized market-data domain."""

from slaifi.domain.assets import AssetClass, AssetId
from slaifi.domain.market.gateway import (
    BarsFetch,
    FetchInfo,
    MarketCache,
    MarketGateway,
    ProviderCheck,
    ProviderPolicy,
    ProviderStatus,
    QuoteFetch,
    SearchFetch,
    SourceAttempt,
)
from slaifi.domain.market.models import (
    AssetRef,
    InstrumentInfo,
    MarketSnapshot,
    OHLCVBar,
    PriceQuote,
)
from slaifi.domain.market.provider import InstrumentSearchProvider, MarketDataProvider

__all__ = [
    "BarsFetch",
    "FetchInfo",
    "MarketCache",
    "MarketGateway",
    "ProviderCheck",
    "ProviderPolicy",
    "ProviderStatus",
    "QuoteFetch",
    "SearchFetch",
    "SourceAttempt",
    "AssetClass",
    "AssetId",
    "AssetRef",
    "InstrumentInfo",
    "InstrumentSearchProvider",
    "MarketDataProvider",
    "MarketSnapshot",
    "OHLCVBar",
    "PriceQuote",
]
