"""Application-owned market-data ports."""

from collections.abc import Sequence
from typing import Protocol

from slaifi.domain.assets import AssetId
from slaifi.domain.market import OHLCVBar, PriceQuote


class MarketReader(Protocol):
    async def get_quotes(self, assets: Sequence[AssetId]) -> Sequence[PriceQuote]:
        """Return normalized quotes."""
        ...

    async def get_bars(self, asset: AssetId, *, limit: int) -> Sequence[OHLCVBar]:
        """Return normalized chronological bars."""
        ...
