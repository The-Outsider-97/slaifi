"""Application service for the Home market overview."""

from dataclasses import dataclass
from datetime import UTC, datetime

from logs.logger import get_logger

from slaifi.core.utils.errors import ValidationError
from slaifi.domain.market.models import AssetRef, PriceQuote
from slaifi.domain.market.provider import MarketDataProvider

logger = get_logger("SLAIFI Market Overview")


@dataclass(frozen=True, slots=True)
class MarketOverview:
    """Provider-neutral market overview returned by the application layer."""

    quotes: tuple[PriceQuote, ...]
    generated_at: datetime


class GetMarketOverview:
    """Orchestrate quote retrieval for the configured Home dashboard universe."""

    def __init__(self, provider: MarketDataProvider, assets: tuple[AssetRef, ...]) -> None:
        if not assets:
            raise ValidationError("market overview requires at least one asset")
        self._provider = provider
        self._assets = assets

    async def execute(self) -> MarketOverview:
        quotes = tuple(await self._provider.get_quotes(self._assets))
        logger.debug("Market overview assembled from %d quote(s)", len(quotes))
        return MarketOverview(quotes=quotes, generated_at=datetime.now(UTC))
