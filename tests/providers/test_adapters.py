"""Each free-tier adapter against a local transport that replays documented response shapes.

These tests prove SLAIFI parses the shapes the providers document and fails safely on their
documented error forms. They do NOT prove the live services still respond this way: run
``POST /api/v1/system/providers/check`` (Settings -> Check providers) with real keys for that.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest

from slaifi.core.utils.errors import (
    MarketDataNotEntitledError,
    MarketDataRateLimitedError,
    MarketDataUnavailableError,
    SymbolNotFoundError,
)
from slaifi.domain.assets import AssetId
from slaifi.infrastructure.market_data.alpha_vantage_provider import AlphaVantageMarketDataProvider
from slaifi.infrastructure.market_data.finnhub_provider import FinnhubMarketDataProvider
from slaifi.infrastructure.market_data.fmp_provider import FmpMarketDataProvider
from slaifi.infrastructure.market_data.tiingo_provider import TiingoMarketDataProvider
from slaifi.infrastructure.market_data.twelve_data_provider import TwelveDataMarketDataProvider

KEY = "SECRET-KEY-123"
AAPL = AssetId("AAPL")
START = datetime(2026, 11, 3, tzinfo=UTC)
END = datetime(2026, 11, 10, tzinfo=UTC)
EPOCH = 1762801800  # 2025-11-10 19:30:00 UTC


class Recorder:
    """Transport that records requests and answers from a handler."""

    def __init__(self, handler: Any) -> None:
        self.requests: list[httpx.Request] = []
        self._handler = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._handler(request)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


def json_response(body: Any, status: int = 200) -> Any:
    return lambda request: httpx.Response(status, json=body)


def build(cls: type, handler: Any) -> tuple[Any, Recorder]:
    rec = Recorder(handler)
    return cls(api_key=KEY, transport=rec.transport), rec


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def quote_of(provider: Any) -> Any:
    quotes = run(provider.get_quotes([AAPL]))
    return quotes[0] if quotes else None


# ============================================================ Twelve Data
TD_QUOTE = {
    "symbol": "AAPL",
    "currency": "USD",
    "timestamp": EPOCH,
    "last_quote_at": EPOCH,
    "close": "228.52",
    "previous_close": "225.70",
    "percent_change": "1.249",
    "is_market_open": False,
}
TD_SERIES = {
    "meta": {"symbol": "AAPL", "interval": "1day"},
    "values": [
        {
            "datetime": "2026-11-04",
            "open": "10",
            "high": "12",
            "low": "9",
            "close": "11",
            "volume": "100",
        },
        {
            "datetime": "2026-11-03",
            "open": "9",
            "high": "11",
            "low": "8",
            "close": "10",
            "volume": "90",
        },
        {
            "datetime": "2026-11-05",
            "open": "11",
            "high": "9",
            "low": "8",
            "close": "10",
            "volume": "1",
        },
    ],
    "status": "ok",
}


def test_twelvedata_quote_parsing_and_key_is_sent_as_parameter() -> None:
    provider, rec = build(TwelveDataMarketDataProvider, json_response(TD_QUOTE))
    q = quote_of(provider)
    assert q.price == Decimal("228.52") and q.previous_close == Decimal("225.70")
    assert q.source == "twelvedata" and q.currency == "USD"
    assert q.change_rate == pytest.approx(0.01249)
    assert q.is_market_open is False
    assert q.observed_at == datetime.fromtimestamp(EPOCH, tz=UTC)
    assert q.last_known is False
    assert rec.requests[0].url.params["apikey"] == KEY


def test_twelvedata_bars_are_sorted_and_inconsistent_rows_dropped() -> None:
    provider, _ = build(TwelveDataMarketDataProvider, json_response(TD_SERIES))
    bars = run(provider.get_bars(AAPL, start_at=START, end_at=END))
    assert [b.close for b in bars] == [Decimal("10"), Decimal("11")]  # high<low row dropped
    assert bars[0].start_at < bars[1].start_at


@pytest.mark.parametrize(
    ("body", "error"),
    [
        (
            {"status": "error", "code": 429, "message": "You have run out of API credits"},
            MarketDataRateLimitedError,
        ),
        (
            {"status": "error", "code": 401, "message": "**apikey** is incorrect"},
            MarketDataUnavailableError,
        ),
        (
            {"status": "error", "code": 403, "message": "available on the Grow plan, upgrade"},
            MarketDataNotEntitledError,
        ),
        ({"status": "error", "code": 404, "message": "symbol not found"}, SymbolNotFoundError),
    ],
)
def test_twelvedata_documented_error_bodies_map_to_typed_errors(body: dict, error: type) -> None:
    provider, _ = build(TwelveDataMarketDataProvider, json_response(body))
    with pytest.raises(error) as caught:
        run(provider.get_quotes([AAPL]))
    assert KEY not in str(caught.value)


# ============================================================ Tiingo
TIINGO_QUOTE = [
    {
        "ticker": "AAPL",
        "timestamp": "2026-11-10T20:59:59+00:00",
        "lastSaleTimestamp": "2026-11-10T20:59:58+00:00",
        "tngoLast": 228.52,
        "last": 228.5,
        "prevClose": 225.7,
    }
]
TIINGO_BARS = [
    {
        "date": "2026-11-03T00:00:00.000Z",
        "close": 100,
        "adjOpen": 9,
        "adjHigh": 11,
        "adjLow": 8,
        "adjClose": 10,
        "adjVolume": 90,
        "open": 90,
        "high": 110,
        "low": 80,
        "volume": 9,
    },
    {
        "date": "2026-11-04T00:00:00.000Z",
        "close": 110,
        "adjOpen": 10,
        "adjHigh": 12,
        "adjLow": 9,
        "adjClose": 11,
        "adjVolume": 100,
        "open": 100,
        "high": 120,
        "low": 90,
        "volume": 10,
    },
]


def test_tiingo_quote_uses_header_auth_and_computes_change_from_prev_close() -> None:
    provider, rec = build(TiingoMarketDataProvider, json_response(TIINGO_QUOTE))
    q = quote_of(provider)
    assert q.price == Decimal("228.52") and q.source == "tiingo"
    assert q.change_rate == pytest.approx(228.52 / 225.7 - 1)
    assert rec.requests[0].headers["Authorization"] == f"Token {KEY}"
    assert KEY not in str(rec.requests[0].url)
    assert rec.requests[0].url.path == "/iex/aapl"


def test_tiingo_history_uses_adjusted_fields() -> None:
    provider, rec = build(TiingoMarketDataProvider, json_response(TIINGO_BARS))
    bars = run(provider.get_bars(AAPL, start_at=START, end_at=END))
    assert [b.close for b in bars] == [Decimal("10"), Decimal("11")]
    assert rec.requests[0].url.params["resampleFreq"] == "daily"


def test_tiingo_no_data_returns_nothing_rather_than_guessing() -> None:
    provider, _ = build(TiingoMarketDataProvider, json_response([]))
    assert quote_of(provider) is None
    provider, _ = build(
        TiingoMarketDataProvider, lambda r: httpx.Response(404, json={"detail": "Not found."})
    )
    with pytest.raises(SymbolNotFoundError):
        run(provider.get_bars(AAPL, start_at=START, end_at=END))


def test_tiingo_intraday_is_not_offered() -> None:
    provider, rec = build(TiingoMarketDataProvider, json_response([]))
    assert run(provider.get_bars(AAPL, start_at=START, end_at=END, interval="1h")) == ()
    assert rec.requests == []
    assert "1h" not in provider.supported_intervals


# ============================================================ Financial Modeling Prep
FMP_QUOTE = [
    {
        "symbol": "AAPL",
        "price": 228.52,
        "changePercentage": 1.249,
        "previousClose": 225.7,
        "timestamp": EPOCH,
    }
]
FMP_BARS = [
    {
        "symbol": "AAPL",
        "date": "2026-11-04",
        "open": 10,
        "high": 12,
        "low": 9,
        "close": 11,
        "volume": 100,
    },
    {
        "symbol": "AAPL",
        "date": "2026-11-03",
        "open": 9,
        "high": 11,
        "low": 8,
        "close": 10,
        "volume": 90,
    },
]


def test_fmp_quote_and_history() -> None:
    provider, rec = build(FmpMarketDataProvider, json_response(FMP_QUOTE))
    q = quote_of(provider)
    assert q.price == Decimal("228.52") and q.source == "fmp"
    assert q.change_rate == pytest.approx(0.01249)
    assert rec.requests[0].url.params["apikey"] == KEY
    provider, _ = build(FmpMarketDataProvider, json_response(FMP_BARS))
    bars = run(provider.get_bars(AAPL, start_at=START, end_at=END))
    assert [b.close for b in bars] == [Decimal("10"), Decimal("11")]


def test_fmp_documented_errors() -> None:
    limit = {"Error Message": "Limit Reach . Please upgrade your plan or visit our documentation"}
    provider, _ = build(FmpMarketDataProvider, json_response(limit))
    with pytest.raises(MarketDataRateLimitedError):
        run(provider.get_quotes([AAPL]))
    provider, _ = build(FmpMarketDataProvider, lambda r: httpx.Response(402, text="premium"))
    with pytest.raises(MarketDataNotEntitledError):
        run(provider.get_quotes([AAPL]))


# ============================================================ Finnhub
def test_finnhub_quote_and_unknown_symbol_zeros() -> None:
    body = {
        "c": 228.52,
        "d": 2.82,
        "dp": 1.249,
        "h": 230,
        "l": 226,
        "o": 227,
        "pc": 225.7,
        "t": EPOCH,
    }
    provider, rec = build(FinnhubMarketDataProvider, json_response(body))
    q = quote_of(provider)
    assert q.price == Decimal("228.52") and q.change_rate == pytest.approx(0.01249)
    assert rec.requests[0].headers["X-Finnhub-Token"] == KEY
    assert KEY not in str(rec.requests[0].url)
    zeros = {"c": 0, "d": None, "dp": None, "h": 0, "l": 0, "o": 0, "pc": 0, "t": 0}
    provider, _ = build(FinnhubMarketDataProvider, json_response(zeros))
    assert quote_of(provider) is None


def test_finnhub_offers_no_history_on_the_free_plan() -> None:
    provider, rec = build(FinnhubMarketDataProvider, json_response({}))
    assert provider.supported_intervals == ()
    assert "bars" not in provider.capabilities
    assert rec.requests == []


def test_finnhub_search() -> None:
    body = {
        "count": 1,
        "result": [{"description": "APPLE INC", "symbol": "AAPL", "type": "Common Stock"}],
    }
    provider, _ = build(FinnhubMarketDataProvider, json_response(body))
    found = run(provider.search_instruments("apple"))
    assert found[0].asset.symbol == "AAPL" and found[0].name == "APPLE INC"


# ============================================================ Alpha Vantage
AV_QUOTE = {
    "Global Quote": {
        "01. symbol": "AAPL",
        "05. price": "228.5200",
        "07. latest trading day": "2026-11-10",
        "08. previous close": "225.7000",
        "10. change percent": "1.2490%",
    }
}
AV_DAILY = {
    "Meta Data": {"2. Symbol": "AAPL"},
    "Time Series (Daily)": {
        "2026-11-04": {
            "1. open": "10",
            "2. high": "12",
            "3. low": "9",
            "4. close": "11",
            "5. volume": "100",
        },
        "2026-11-03": {
            "1. open": "9",
            "2. high": "11",
            "3. low": "8",
            "4. close": "10",
            "5. volume": "90",
        },
        "2026-10-01": {
            "1. open": "1",
            "2. high": "2",
            "3. low": "1",
            "4. close": "2",
            "5. volume": "1",
        },
    },
}


def test_alphavantage_quote_is_marked_delayed_and_dated_to_the_trading_day() -> None:
    provider, rec = build(AlphaVantageMarketDataProvider, json_response(AV_QUOTE))
    q = quote_of(provider)
    assert q.price == Decimal("228.52") and q.delayed is True and q.source == "alphavantage"
    assert q.observed_at == datetime(2026, 11, 10, tzinfo=UTC)
    assert q.change_rate == pytest.approx(0.01249)
    assert rec.requests[0].url.params["function"] == "GLOBAL_QUOTE"


def test_alphavantage_history_is_clipped_to_requested_window() -> None:
    provider, _ = build(AlphaVantageMarketDataProvider, json_response(AV_DAILY))
    bars = run(provider.get_bars(AAPL, start_at=START, end_at=END))
    assert [b.close for b in bars] == [Decimal("10"), Decimal("11")]


def test_alphavantage_throttle_notice_is_a_rate_limit_not_data() -> None:
    notice = {
        "Information": "Thank you for using Alpha Vantage! Our standard API rate limit is 25 requests per day."
    }
    provider, _ = build(AlphaVantageMarketDataProvider, json_response(notice))
    with pytest.raises(MarketDataRateLimitedError):
        run(provider.get_quotes([AAPL]))


def test_alphavantage_empty_global_quote_is_no_data() -> None:
    provider, _ = build(AlphaVantageMarketDataProvider, json_response({"Global Quote": {}}))
    assert quote_of(provider) is None


# ============================================================ shared behaviour
ALL = [
    (TwelveDataMarketDataProvider, TD_QUOTE),
    (TiingoMarketDataProvider, TIINGO_QUOTE),
    (FmpMarketDataProvider, FMP_QUOTE),
    (FinnhubMarketDataProvider, {"c": 1, "pc": 1, "dp": 0, "t": EPOCH}),
    (AlphaVantageMarketDataProvider, AV_QUOTE),
]


@pytest.mark.parametrize(("cls", "body"), ALL)
def test_http_failures_never_leak_the_key_and_are_typed(cls: type, body: Any) -> None:
    provider, _ = build(cls, lambda r: httpx.Response(500, text=f"boom {r.url}"))
    with pytest.raises(MarketDataUnavailableError) as caught:
        run(provider.get_quotes([AAPL]))
    assert KEY not in str(caught.value)

    provider, _ = build(cls, lambda r: httpx.Response(429, headers={"Retry-After": "12"}))
    with pytest.raises(MarketDataRateLimitedError) as limited:
        run(provider.get_quotes([AAPL]))
    assert limited.value.retry_after_seconds == 12

    provider, _ = build(cls, lambda r: httpx.Response(401, json={}))
    with pytest.raises(MarketDataUnavailableError) as rejected:
        run(provider.get_quotes([AAPL]))
    assert rejected.value.retryable is False and KEY not in str(rejected.value)


@pytest.mark.parametrize(("cls", "body"), ALL)
def test_transport_errors_and_garbage_are_typed(cls: type, body: Any) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    provider, _ = build(cls, boom)
    with pytest.raises(MarketDataUnavailableError) as caught:
        run(provider.get_quotes([AAPL]))
    assert KEY not in str(caught.value)
    provider, _ = build(cls, lambda r: httpx.Response(200, text="<html>not json</html>"))
    with pytest.raises(MarketDataUnavailableError):
        run(provider.get_quotes([AAPL]))


@pytest.mark.parametrize(("cls", "body"), ALL)
def test_blank_key_is_rejected_at_construction(cls: type, body: Any) -> None:
    with pytest.raises(ValueError):
        cls(api_key="   ")


def test_five_distinct_providers_are_implemented() -> None:
    names = {cls.name for cls, _ in ALL}
    assert names == {"twelvedata", "tiingo", "fmp", "finnhub", "alphavantage"}
    assert len({cls.default_base_url for cls, _ in ALL}) == 5


def test_request_budget_stops_calls_before_the_free_tier_is_exhausted() -> None:
    provider, rec = build(AlphaVantageMarketDataProvider, json_response(AV_QUOTE))
    served = 0
    with pytest.raises(MarketDataRateLimitedError) as caught:
        for _ in range(10):
            run(provider.get_quotes([AAPL]))
            served += 1
    assert served == 5 and len(rec.requests) == 5  # 5 per minute, enforced locally
    assert "alphavantage" in str(caught.value).lower() or caught.value.component == "alphavantage"
