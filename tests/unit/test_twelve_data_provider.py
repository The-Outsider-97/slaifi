import asyncio
from datetime import timedelta
from decimal import Decimal

import pytest

from slaifi.core.types import CurrencyCode
from slaifi.domain.assets import AssetId
from slaifi.domain.market.models import PriceQuote
from slaifi.infrastructure.market_data.twelve_data_provider import TwelveDataMarketDataProvider


def test_market_interval_duration_is_not_hardcoded_to_one_day() -> None:
    assert TwelveDataMarketDataProvider._interval_delta("5min") == timedelta(minutes=5)
    assert TwelveDataMarketDataProvider._interval_delta("4h") == timedelta(hours=4)
    assert TwelveDataMarketDataProvider._interval_delta("1day") == timedelta(days=1)
    assert TwelveDataMarketDataProvider._interval_delta("1week") == timedelta(weeks=1)


def test_unsupported_market_interval_fails_explicitly() -> None:
    with pytest.raises(ValueError, match="unsupported market interval"):
        TwelveDataMarketDataProvider._interval_delta("1month")


def test_duplicate_assets_are_fetched_once_per_quote_request(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = TwelveDataMarketDataProvider(
        api_key="test-key",
        quote_cache_ttl_seconds=0,
        history_cache_ttl_seconds=0,
    )
    asset = AssetId(symbol="ABC")
    calls: list[AssetId] = []

    async def fake_get_quote(requested: AssetId) -> PriceQuote:
        calls.append(requested)
        from datetime import UTC, datetime

        return PriceQuote(
            asset=requested,
            price=Decimal("10"),
            currency=CurrencyCode("USD"),
            observed_at=datetime(2026, 1, 1, tzinfo=UTC),
            source="test",
        )

    monkeypatch.setattr(provider, "_get_quote", fake_get_quote)
    try:
        quotes = asyncio.run(provider.get_quotes((asset, asset)))
    finally:
        asyncio.run(provider.close())

    assert calls == [asset]
    assert len(quotes) == 2
    assert quotes[0] == quotes[1]
