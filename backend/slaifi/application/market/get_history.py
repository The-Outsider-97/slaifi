"""Historical market-series application service."""

from dataclasses import dataclass
from datetime import UTC, datetime

from slaifi.core.utils.errors import ValidationError
from slaifi.domain.assets import AssetId
from slaifi.domain.market.models import OHLCVBar
from slaifi.domain.market.provider import MarketDataProvider


@dataclass(frozen=True, slots=True)
class MarketHistory:
    asset: AssetId
    interval: str
    bars: tuple[OHLCVBar, ...]
    generated_at: datetime
    data_mode: str


class GetMarketHistory:
    """Retrieve normalized historical bars from the configured provider."""

    def __init__(self, provider: MarketDataProvider) -> None:
        self._provider = provider

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

        bars = tuple(
            await self._provider.get_bars(
                asset,
                start_at=start_at,
                end_at=end_at,
                interval=interval,
            )
        )

        return MarketHistory(
            asset=asset,
            interval=interval,
            bars=bars,
            generated_at=datetime.now(UTC),
            data_mode=getattr(
                self._provider,
                "data_mode",
                "unknown",
            ),
        )
