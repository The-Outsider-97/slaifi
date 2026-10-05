"""Market-provider contract owned by the SLAIFI domain."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from slaifi.domain.assets import AssetId
from slaifi.domain.market.models import OHLCVBar, PriceQuote


class MarketDataProvider(Protocol):
    """Provider-neutral market data contract."""
    data_mode: str

    async def get_quotes(self, assets: Sequence[AssetId]) -> Sequence[PriceQuote]:
        ...

    async def get_bars(self, asset: AssetId, *, start_at: datetime, end_at: datetime, interval: str = "1day") -> Sequence[OHLCVBar]:
        ...
