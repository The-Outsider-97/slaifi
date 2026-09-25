import asyncio
from decimal import Decimal

from slaifi.domain.market.models import AssetRef
from slaifi.infrastructure.market_data.mock_provider import MockMarketDataProvider


def test_mock_provider_normalizes_provider_payload() -> None:
    quotes = asyncio.run(MockMarketDataProvider().get_quotes([AssetRef("spy")]))

    assert len(quotes) == 1
    quote = quotes[0]
    assert quote.asset.symbol == "SPY"
    assert quote.price == Decimal("100.00")
    assert quote.currency == "USD"
    assert quote.source == "mock"
    assert quote.observed_at.tzinfo is not None
