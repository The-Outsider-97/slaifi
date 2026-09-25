"""Market-provider contract owned by the SLAIFI domain."""

from collections.abc import Sequence
from typing import Protocol

from slaifi.domain.assets import AssetId
from slaifi.domain.market.models import PriceQuote


class MarketDataProvider(Protocol):
    async def get_quotes(self, assets: Sequence[AssetId]) -> Sequence[PriceQuote]: ...
