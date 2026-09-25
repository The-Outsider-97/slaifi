from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from slaifi.application.market.get_overview import GetMarketOverview
from slaifi.domain.market.models import AssetRef, PriceQuote


class StubProvider:
    async def get_quotes(self, assets: Sequence[AssetRef]) -> Sequence[PriceQuote]:
        return [
            PriceQuote(
                asset=asset,
                price=Decimal("123.45"),
                currency="USD",
                observed_at=datetime(2026, 9, 25, tzinfo=UTC),
                source="stub",
                change_percent=Decimal("1.25"),
            )
            for asset in assets
        ]


@pytest.mark.asyncio
async def test_market_overview_uses_provider_and_preserves_normalized_quotes() -> None:
    service = GetMarketOverview(StubProvider(), (AssetRef("spy"), AssetRef("qqq")))

    overview = await service.execute()

    assert [quote.asset.symbol for quote in overview.quotes] == ["SPY", "QQQ"]
    assert all(quote.price == Decimal("123.45") for quote in overview.quotes)
    assert overview.generated_at.tzinfo is not None
