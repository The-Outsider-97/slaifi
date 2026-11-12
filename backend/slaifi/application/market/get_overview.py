"""Application service for the Market Overview dashboard."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from logs.logger import get_logger

from slaifi.core.utils.errors import ValidationError
from slaifi.domain.assets import AssetId
from slaifi.domain.market import MarketGateway
from slaifi.domain.market.models import AssetRef, PriceQuote

logger = get_logger("SLAIFI Market Overview")


@dataclass(frozen=True, slots=True)
class MarketOverview:
    """Provider-neutral market overview.

    ``quotes`` holds every instrument for which a real observation exists (live, or the last
    known one, flagged on the quote). ``unavailable`` lists instruments with nothing at all.
    """

    quotes: tuple[PriceQuote, ...]
    unavailable: tuple[str, ...]
    generated_at: datetime
    data_mode: str  # live | delayed | live_delay_unknown | last_known | unavailable


def overview_mode(quotes: tuple[PriceQuote, ...]) -> str:
    if not quotes:
        return "unavailable"
    if any(q.last_known for q in quotes):
        return "last_known"
    if all(q.delayed is True for q in quotes):
        return "delayed"
    if all(q.delayed is False for q in quotes):
        return "live"
    return "live_delay_unknown"


class GetMarketOverview:
    """Retrieve the configured dashboard market universe."""

    def __init__(
        self,
        gateway: MarketGateway,
        assets: tuple[AssetRef, ...],
        *,
        classify: Callable[[str], Awaitable[AssetId]] | None = None,
    ) -> None:
        if not assets:
            raise ValidationError("market overview requires at least one asset")
        self._gateway = gateway
        self._assets = assets
        self._classify = classify

    async def _identified(self) -> tuple[AssetId, ...]:
        """Attach the asset class (ETF, index, stock…) found by instrument search.

        Only the class is kept: exchange and currency are left to the quote providers, so a
        same-ticker listing on another exchange can never change the price that is requested.
        """

        if self._classify is None:
            return tuple(self._assets)
        classify = self._classify

        async def one(asset: AssetId) -> AssetId:
            try:
                found = await classify(asset.symbol)
            except Exception:  # noqa: BLE001 - classification is cosmetic; quotes must still work
                return asset
            return AssetId(asset.symbol, found.asset_class)

        return tuple(await asyncio.gather(*(one(a) for a in self._assets)))

    async def execute(self) -> MarketOverview:
        fetched = await self._gateway.fetch_quotes(await self._identified())
        quotes = tuple(f.quote for f in fetched if f.quote is not None)
        missing = tuple(f.asset.symbol for f in fetched if f.quote is None)
        logger.debug(
            "Market overview assembled from %d quote(s), %d unavailable", len(quotes), len(missing)
        )
        return MarketOverview(
            quotes=quotes,
            unavailable=missing,
            generated_at=datetime.now(UTC),
            data_mode=overview_mode(quotes),
        )
