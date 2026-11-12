"""Market-data provider adapters, the failover gateway and the last-known cache."""

from slaifi.infrastructure.market_data.alpha_vantage_provider import AlphaVantageMarketDataProvider
from slaifi.infrastructure.market_data.factory import KEY_ENV, PROVIDER_CLASSES, build_gateway
from slaifi.infrastructure.market_data.finnhub_provider import FinnhubMarketDataProvider
from slaifi.infrastructure.market_data.fmp_provider import FmpMarketDataProvider
from slaifi.infrastructure.market_data.gateway import MultiSourceGateway
from slaifi.infrastructure.market_data.memory_cache import InMemoryMarketCache
from slaifi.infrastructure.market_data.tiingo_provider import TiingoMarketDataProvider
from slaifi.infrastructure.market_data.twelve_data_provider import TwelveDataMarketDataProvider

__all__ = [
    "KEY_ENV",
    "PROVIDER_CLASSES",
    "AlphaVantageMarketDataProvider",
    "FinnhubMarketDataProvider",
    "FmpMarketDataProvider",
    "InMemoryMarketCache",
    "MultiSourceGateway",
    "TiingoMarketDataProvider",
    "TwelveDataMarketDataProvider",
    "build_gateway",
]
