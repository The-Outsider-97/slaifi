import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from slaifi.core.utils.errors import InfrastructureError
from slaifi.domain.assets import AssetId
from slaifi.infrastructure.market_data.twelve_data_provider import TwelveDataMarketDataProvider


def run(coro):
    return asyncio.run(coro)


def provider_with_transport(handler: httpx.MockTransport) -> TwelveDataMarketDataProvider:
    provider = TwelveDataMarketDataProvider(
        api_key="test-key",
        quote_cache_ttl_seconds=30,
        history_cache_ttl_seconds=30,
    )
    run(provider._client.aclose())
    provider._client = httpx.AsyncClient(
        base_url="https://api.twelvedata.com",
        transport=handler,
    )
    return provider


def test_quote_requests_are_coalesced_by_short_ttl_cache() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path == "/quote"
        return httpx.Response(
            200,
            json={
                "symbol": "SPY",
                "close": "100.50",
                "percent_change": "0.25",
                "currency": "USD",
                "timestamp": "1791200000",
            },
        )

    provider = provider_with_transport(httpx.MockTransport(handler))
    asset = AssetId("SPY")
    try:
        first = run(provider.get_quotes([asset]))
        second = run(provider.get_quotes([asset]))
    finally:
        run(provider.close())

    assert calls == 1
    assert first[0].price == second[0].price
    assert first[0].source == "twelvedata"


def test_history_requests_use_bounded_cache_without_inventing_points() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path == "/time_series"
        return httpx.Response(
            200,
            json={
                "values": [
                    {
                        "datetime": "2026-10-01",
                        "open": "100",
                        "high": "103",
                        "low": "99",
                        "close": "102",
                        "volume": "1000",
                    },
                    {
                        "datetime": "2026-10-02",
                        "open": "102",
                        "high": "104",
                        "low": "101",
                        "close": "103",
                        "volume": "1200",
                    },
                ]
            },
        )

    provider = provider_with_transport(httpx.MockTransport(handler))
    asset = AssetId("SPY")
    start = datetime(2026, 10, 1, tzinfo=UTC)
    end = datetime(2026, 10, 3, tzinfo=UTC)
    try:
        first = run(provider.get_bars(asset, start_at=start, end_at=end))
        second = run(provider.get_bars(asset, start_at=start, end_at=end))
    finally:
        run(provider.close())

    assert calls == 1
    assert len(first) == 2
    assert first == second
    assert [str(bar.close) for bar in first] == ["102", "103"]


def test_provider_failure_is_translated_without_exposing_credentials() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"status": "error", "message": "rate limited"})

    provider = provider_with_transport(httpx.MockTransport(handler))
    try:
        with pytest.raises(InfrastructureError) as captured:
            run(provider.get_quotes([AssetId("SPY")]))
    finally:
        run(provider.close())

    error = captured.value
    assert error.component == "market_data"
    assert error.operation == "quote"
    assert error.retryable is True
    assert "test-key" not in str(error)
