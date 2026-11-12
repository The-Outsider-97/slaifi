"""Failover, cool-down, coverage, last-known and NOT-AVAILABLE behaviour of the gateway."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from slaifi.core.utils.errors import (
    MarketDataNotEntitledError,
    MarketDataRateLimitedError,
    MarketDataUnavailableError,
    SymbolNotFoundError,
)
from slaifi.domain.assets import AssetId
from slaifi.domain.market import InstrumentInfo, OHLCVBar, PriceQuote, ProviderPolicy
from slaifi.infrastructure.market_data import InMemoryMarketCache
from slaifi.infrastructure.market_data.base import RequestBudget
from slaifi.infrastructure.market_data.gateway import (
    DEFAULT_COOLDOWN_SECONDS,
    MultiSourceGateway,
)

AAPL = AssetId("AAPL")
T0 = datetime(2026, 11, 10, 15, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def make_quote(price: str, source: str, at: datetime = T0) -> PriceQuote:
    return PriceQuote(
        asset=AAPL,
        price=Decimal(price),
        currency="USD",
        observed_at=at,
        source=source,
        delayed=False,
    )


def make_bars(count: int, end: datetime = T0, *, close: str = "10") -> tuple[OHLCVBar, ...]:
    out = []
    for i in range(count):
        start = (end - timedelta(days=count - i)).replace(hour=0, minute=0, second=0, microsecond=0)
        out.append(
            OHLCVBar(
                asset=AAPL,
                start_at=start,
                end_at=start + timedelta(days=1),
                open=Decimal(close),
                high=Decimal(close) + 1,
                low=Decimal(close) - 1,
                close=Decimal(close),
                volume=Decimal(100),
            )
        )
    return tuple(out)


class Fake:
    """A provider whose behaviour is scripted per call: a value, or an exception to raise."""

    capabilities: tuple[str, ...] = ("quotes", "bars", "search")
    supported_intervals: tuple[str, ...] = ("1day",)
    data_mode = "live"

    def __init__(
        self, name: str, *, quote: Any = None, bars: Any = (), search: Any = (), **kw: Any
    ):
        self.name = name
        self.label = name.title()
        self.quote, self.bars, self.search = quote, bars, search
        self.policy = ProviderPolicy(note=f"{name} test plan")
        self.budget = RequestBudget(self.policy)
        self.calls = 0
        self.capabilities = kw.get("capabilities", self.capabilities)
        self.supported_intervals = kw.get("intervals", self.supported_intervals)

    @staticmethod
    def _out(value: Any) -> Any:
        if isinstance(value, Exception):
            raise value
        return value

    async def get_quotes(self, assets: Any) -> Any:
        self.calls += 1
        value = self._out(self.quote)
        return () if value is None else (value,)

    async def get_bars(
        self, asset: Any, *, start_at: Any, end_at: Any, interval: str = "1day"
    ) -> Any:
        self.calls += 1
        return self._out(self.bars)

    async def search_instruments(self, query: str, *, limit: int = 10) -> Any:
        self.calls += 1
        return self._out(self.search)

    async def close(self) -> None:
        return None


def gateway(*providers: Fake, cache: Any = "default", clock: Clock | None = None, **kw: Any):
    clock = clock or Clock()
    cache = InMemoryMarketCache() if cache == "default" else cache
    kw.setdefault("quote_ttl_seconds", 0.0)
    kw.setdefault("history_ttl_seconds", 0.0)
    return MultiSourceGateway(list(providers), cache=cache, clock=clock, **kw), clock


def quote_of(gw: MultiSourceGateway) -> Any:
    return asyncio.run(gw.fetch_quotes([AAPL]))[0]


def bars_of(gw: MultiSourceGateway, days: int = 30, **kw: Any) -> Any:
    return asyncio.run(gw.fetch_bars(AAPL, start_at=T0 - timedelta(days=days), end_at=T0, **kw))


# ------------------------------------------------------------------ quotes
def test_first_working_provider_in_priority_order_wins() -> None:
    a, b = Fake("a", quote=make_quote("1", "a")), Fake("b", quote=make_quote("2", "b"))
    result = quote_of(gateway(a, b)[0])
    assert result.quote.price == Decimal("1") and result.info.source == "a"
    assert result.quote.last_known is False
    assert b.calls == 0  # free-tier budget is not spent when the first source answers


@pytest.mark.parametrize(
    "failure",
    [
        MarketDataRateLimitedError("limit", component="a"),
        MarketDataUnavailableError("down", component="a"),
        MarketDataNotEntitledError("premium", component="a"),
        SymbolNotFoundError("nope", component="a"),
        RuntimeError("adapter bug"),
    ],
)
def test_any_failure_falls_through_to_the_next_provider(failure: Exception) -> None:
    a, b = Fake("a", quote=failure), Fake("b", quote=make_quote("2", "b"))
    result = quote_of(gateway(a, b)[0])
    assert result.quote.price == Decimal("2") and result.info.source == "b"
    assert [x.source for x in result.info.attempts] == ["a", "b"]
    assert result.info.attempts[-1].outcome == "ok" and result.info.attempts[0].outcome != "ok"


def test_three_providers_each_in_turn() -> None:
    a = Fake("a", quote=MarketDataUnavailableError("x", component="a"))
    b = Fake("b", quote=MarketDataRateLimitedError("y", component="b"))
    c = Fake("c", quote=make_quote("3", "c"))
    result = quote_of(gateway(a, b, c)[0])
    assert result.info.source == "c"
    assert [x.outcome for x in result.info.attempts] == ["unavailable", "rate_limited", "ok"]


def test_failed_provider_cools_down_then_is_retried() -> None:
    a = Fake("a", quote=MarketDataUnavailableError("down", component="a"))
    b = Fake("b", quote=make_quote("2", "b"))
    gw, clock = gateway(a, b)
    quote_of(gw)
    quote_of(gw)
    assert a.calls == 1  # second request skipped "a" during its cool-down
    status = {s.name: s for s in gw.provider_status()}
    assert status["a"].state == "cooling_down" and status["a"].last_error == "down"
    clock.advance(DEFAULT_COOLDOWN_SECONDS + 1)
    a.quote = make_quote("1", "a")
    assert quote_of(gw).info.source == "a" and a.calls == 2
    assert {s.name: s for s in gw.provider_status()}["a"].state == "ready"


def test_rate_limit_uses_the_providers_retry_after() -> None:
    a = Fake("a", quote=MarketDataRateLimitedError("limit", retry_after_seconds=300, component="a"))
    gw, clock = gateway(a, Fake("b", quote=make_quote("2", "b")))
    quote_of(gw)
    clock.advance(120)
    quote_of(gw)
    assert a.calls == 1
    clock.advance(200)
    a.quote = make_quote("1", "a")
    assert quote_of(gw).info.source == "a"


def test_a_rejected_key_is_not_retried() -> None:
    a = Fake("a", quote=MarketDataUnavailableError("bad key", component="a", retryable=False))
    gw, clock = gateway(a, Fake("b", quote=make_quote("2", "b")))
    quote_of(gw)
    clock.advance(3600)
    quote_of(gw)
    assert a.calls == 1
    assert {s.name: s for s in gw.provider_status()}["a"].state == "rejected_credentials"


def test_quote_time_in_the_future_is_refused() -> None:
    future = make_quote("1", "a", at=T0 + timedelta(hours=2))
    result = quote_of(gateway(Fake("a", quote=future), cache=None)[0])
    assert result.quote is None


def test_providers_without_a_capability_are_not_asked() -> None:
    a = Fake("a", quote=make_quote("1", "a"), capabilities=("bars",))
    b = Fake("b", quote=make_quote("2", "b"))
    assert quote_of(gateway(a, b)[0]).info.source == "b" and a.calls == 0


# ------------------------------------------------------------------ last known / NOT AVAILABLE
def test_when_every_source_fails_the_last_real_quote_is_served_and_flagged() -> None:
    a = Fake("a", quote=make_quote("1", "a"))
    gw, clock = gateway(a)
    assert quote_of(gw).quote.last_known is False
    clock.advance(3600)
    a.quote = MarketDataUnavailableError("down", component="a")
    result = quote_of(gw)
    assert result.quote.last_known is True and result.info.last_known is True
    assert result.quote.price == Decimal("1")
    assert result.quote.observed_at == T0  # the original observation time, not "now"
    assert result.info.saved_at == T0 and result.info.source == "a"


def test_nothing_live_and_nothing_saved_is_not_available() -> None:
    a = Fake("a", quote=MarketDataUnavailableError("down", component="a"))
    result = quote_of(gateway(a)[0])
    assert result.quote is None and result.info.source is None
    assert result.info.attempts[0].outcome == "unavailable"


def test_no_cache_and_no_providers_is_not_available() -> None:
    assert quote_of(gateway(cache=None)[0]).quote is None


def test_older_observation_never_overwrites_a_newer_saved_one() -> None:
    cache = InMemoryMarketCache()
    cache.save_quote(make_quote("5", "a", at=T0), saved_at=T0)
    cache.save_quote(make_quote("4", "a", at=T0 - timedelta(days=1)), saved_at=T0)
    assert cache.load_quote(AAPL)[0].price == Decimal("5")


def test_quote_cache_failure_never_breaks_live_data() -> None:
    class Broken:
        def save_quote(self, *a: Any, **k: Any) -> None:
            raise OSError("disk full")

        def load_quote(self, *a: Any, **k: Any) -> Any:
            raise OSError("disk full")

    result = quote_of(gateway(Fake("a", quote=make_quote("1", "a")), cache=Broken())[0])
    assert result.quote.price == Decimal("1")
    down = quote_of(
        gateway(Fake("a", quote=MarketDataUnavailableError("x", component="a")), cache=Broken())[0]
    )
    assert down.quote is None


def test_short_ttl_cache_avoids_a_second_api_call() -> None:
    a = Fake("a", quote=make_quote("1", "a"))
    gw, _ = gateway(a, quote_ttl_seconds=60.0)
    quote_of(gw)
    quote_of(gw)
    assert a.calls == 1


# ------------------------------------------------------------------ history
def test_history_failover_and_last_known() -> None:
    a = Fake("a", bars=MarketDataUnavailableError("down", component="a"))
    b = Fake("b", bars=make_bars(30))
    gw, _ = gateway(a, b)
    live = bars_of(gw)
    assert len(live.bars) == 30 and live.info.source == "b" and live.info.last_known is False
    b.bars = MarketDataUnavailableError("down", component="b")
    clock_later = bars_of(gw)
    assert len(clock_later.bars) > 0 and clock_later.info.last_known is True
    assert clock_later.info.source == "b"


def test_history_that_does_not_reach_back_far_enough_tries_the_next_source() -> None:
    short = Fake("alphavantage_like", bars=make_bars(10))
    full = Fake("full", bars=make_bars(120))
    result = bars_of(gateway(short, full)[0], days=120)
    assert result.info.source == "full" and len(result.bars) == 120
    assert short.calls == 1 and full.calls == 1
    assert "partial history" in (result.info.attempts[0].detail or "")


def test_if_no_source_reaches_back_the_longest_real_series_is_returned_not_padded() -> None:
    a, b = Fake("a", bars=make_bars(10)), Fake("b", bars=make_bars(25))
    result = bars_of(gateway(a, b)[0], days=200)
    assert result.info.source == "b" and len(result.bars) == 25


def test_unsupported_interval_asks_nobody_and_returns_nothing() -> None:
    a = Fake("a", bars=make_bars(10))
    result = bars_of(gateway(a, cache=None)[0], interval="1h")
    assert result.bars == () and a.calls == 0


def test_saved_bars_from_different_sources_are_not_mixed() -> None:
    cache = InMemoryMarketCache()
    cache.save_bars(AAPL, "1day", make_bars(5, close="10"), source="a", saved_at=T0)
    cache.save_bars(AAPL, "1day", make_bars(5, close="99"), source="b", saved_at=T0)
    bars, source, _ = cache.load_bars(AAPL, "1day", start_at=T0 - timedelta(days=30), end_at=T0)
    assert len(bars) == 5 and len({b.close for b in bars}) == 1 and source in {"a", "b"}


# ------------------------------------------------------------------ search
def _info(symbol: str) -> InstrumentInfo:
    return InstrumentInfo(asset=AssetId(symbol), name=symbol + " Inc")


def test_search_fails_over_and_falls_back_to_saved_results() -> None:
    a = Fake("a", search=MarketDataUnavailableError("down", component="a"))
    b = Fake("b", search=(_info("AAPL"),))
    gw, _ = gateway(a, b)
    first = asyncio.run(gw.fetch_search("apple"))
    assert first.results[0].asset.symbol == "AAPL" and first.info.source == "b"
    b.search = MarketDataUnavailableError("down", component="b")
    later = asyncio.run(gw.fetch_search("apple"))
    assert later.results and later.info.last_known is True


def test_search_with_nothing_is_empty() -> None:
    a = Fake("a", search=MarketDataUnavailableError("down", component="a"))
    assert asyncio.run(gateway(a)[0].fetch_search("zzz")).results == ()


# ------------------------------------------------------------------ status and checks
def test_status_reports_configured_and_unconfigured_providers() -> None:
    from slaifi.infrastructure.market_data.fmp_provider import FmpMarketDataProvider

    gw = MultiSourceGateway(
        [Fake("a", quote=make_quote("1", "a"))],  # type: ignore[list-item]
        unconfigured=[FmpMarketDataProvider],
        cache=None,
    )
    rows = {r.name: r for r in gw.provider_status()}
    assert rows["a"].configured is True and rows["a"].state == "ready"
    assert rows["fmp"].configured is False and rows["fmp"].state == "not_configured"
    assert gw.configured is True
    assert MultiSourceGateway([], cache=None).configured is False


def test_check_providers_makes_one_real_call_each_and_reports_failures() -> None:
    a = Fake("a", quote=make_quote("228.5", "a"))
    b = Fake("b", quote=MarketDataUnavailableError("HTTP 500", component="b"))
    gw, _ = gateway(a, b)
    checks = {c.name: c for c in asyncio.run(gw.check_providers())}
    assert checks["a"].ok is True and "228.5" in checks["a"].detail
    assert checks["b"].ok is False and "HTTP 500" in checks["b"].detail
    assert a.calls == 1 and b.calls == 1


def test_request_budget_blocks_before_the_free_tier_limit() -> None:
    now = [0.0]
    budget = RequestBudget(ProviderPolicy(per_minute=2), lambda: now[0])
    budget.acquire(source="x")
    budget.acquire(source="x")
    with pytest.raises(MarketDataRateLimitedError):
        budget.acquire(source="x")
    now[0] = 61.0
    budget.acquire(source="x")


def test_resolution_prefers_the_us_listing_of_a_shared_ticker() -> None:
    from slaifi.application.market import MarketDataService
    from slaifi.domain.assets import AssetClass

    mexico = InstrumentInfo(
        asset=AssetId("SPY", AssetClass.ETF, "BMV", "MXN"), name="SPY Mexico", country="Mexico"
    )
    us = InstrumentInfo(
        asset=AssetId("SPY", AssetClass.ETF, "NYSE", "USD"),
        name="SPDR S&P 500 ETF Trust",
        country="United States",
    )
    gw, _ = gateway(Fake("a", search=(mexico, us)))
    resolved = asyncio.run(MarketDataService(gw).resolve_asset("spy"))
    assert resolved.exchange == "NYSE" and resolved.currency == "USD"


def test_one_history_request_serves_the_short_and_the_long_views() -> None:
    """3M chart, 1Y statistics and 2Y recommendation must not cost three API calls."""

    full = Fake("a", bars=make_bars(700))
    gw, _ = gateway(full, history_ttl_seconds=300.0)
    three_months = bars_of(gw, days=93)
    one_year = bars_of(gw, days=365)
    two_years = bars_of(gw, days=730)
    assert full.calls == 1
    assert 80 <= len(three_months.bars) <= 95
    assert len(one_year.bars) > len(three_months.bars)
    assert len(two_years.bars) > len(one_year.bars)
    assert three_months.info.source == "a" and three_months.info.last_known is False


def test_history_is_requested_wide_but_judged_against_the_requested_start() -> None:
    seen: list[datetime] = []

    class Recording(Fake):
        async def get_bars(
            self, asset: Any, *, start_at: Any, end_at: Any, interval: str = "1day"
        ) -> Any:
            seen.append(start_at)
            return await super().get_bars(
                asset, start_at=start_at, end_at=end_at, interval=interval
            )

    a = Recording("a", bars=make_bars(40))  # only ~40 days: enough for 30, not for 730
    b = Fake("b", bars=make_bars(300))
    result = bars_of(gateway(a, b)[0], days=200)
    assert (T0 - seen[0]).days >= 760  # asked wide
    assert result.info.source == "b" and len(result.bars) >= 190  # a was partial for 200 days
