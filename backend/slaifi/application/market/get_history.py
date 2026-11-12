"""Historical market-series application service."""

from dataclasses import dataclass
from datetime import UTC, datetime

from slaifi.core.utils.errors import ValidationError
from slaifi.domain.assets import AssetId
from slaifi.domain.market import MarketGateway
from slaifi.domain.market.models import OHLCVBar


@dataclass(frozen=True, slots=True)
class MarketHistory:
    asset: AssetId
    interval: str
    bars: tuple[OHLCVBar, ...]
    generated_at: datetime
    data_mode: str  # retrieved | last_known | unavailable
    source: str | None = None
    last_known: bool = False
    saved_at: datetime | None = None


class GetMarketHistory:
    """Retrieve normalized historical bars through the multi-source gateway."""

    def __init__(self, gateway: MarketGateway) -> None:
        self._gateway = gateway

    async def execute(
        self,
        asset: AssetId,
        *,
        start_at: datetime,
        end_at: datetime,
        interval: str = "1day",
    ) -> MarketHistory:
        if start_at.tzinfo is None or start_at.utcoffset() is None:
            raise ValidationError("start_at must be timezone-aware")
        if end_at.tzinfo is None or end_at.utcoffset() is None:
            raise ValidationError("end_at must be timezone-aware")
        if end_at <= start_at:
            raise ValidationError("end_at must be later than start_at")
        fetch = await self._gateway.fetch_bars(
            asset, start_at=start_at, end_at=end_at, interval=interval
        )
        if not fetch.bars:
            mode = "unavailable"
        elif fetch.info.last_known:
            mode = "last_known"
        else:
            mode = "retrieved"
        return MarketHistory(
            asset=asset,
            interval=interval,
            bars=tuple(fetch.bars),
            generated_at=datetime.now(UTC),
            data_mode=mode,
            source=fetch.info.source,
            last_known=fetch.info.last_known,
            saved_at=fetch.info.saved_at,
        )
