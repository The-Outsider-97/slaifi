"""Market provider contract owned by the SLAIFI domain."""

from collections.abc import Sequence
from typing import Protocol

from slaifi.domain.market.models import AssetRef, PriceQuote


class MarketDataProvider(Protocol):
    """Retrieve normalized market observations without exposing vendor payloads."""

    async def get_quotes(self, assets: Sequence[AssetRef]) -> Sequence[PriceQuote]:
        """Return normalized quotes for the requested assets."""
        ...
