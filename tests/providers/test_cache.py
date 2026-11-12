"""The last-known cache contract, run against the in-memory and the SQLite implementations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from slaifi.domain.assets import AssetClass, AssetId
from slaifi.domain.market import InstrumentInfo, OHLCVBar, PriceQuote
from slaifi.infrastructure.market_data import InMemoryMarketCache

T0 = datetime(2026, 11, 10, 15, 0, tzinfo=UTC)
KO = AssetId("KO", AssetClass.EQUITY, "NYSE", "USD")


def quote(price: str = "60.25", at: datetime = T0, source: str = "tiingo") -> PriceQuote:
    return PriceQuote(
        asset=KO,
        price=Decimal(price),
        currency="USD",
        observed_at=at,
        source=source,
        change_rate=0.0123,
        is_market_open=False,
        delayed=True,
        previous_close=Decimal("59.5"),
    )


def bars(count: int, close: str = "60") -> tuple[OHLCVBar, ...]:
    out = []
    for i in range(count):
        s = datetime(2026, 10, 1, tzinfo=UTC) + timedelta(days=i)
        out.append(
            OHLCVBar(
                asset=KO,
                start_at=s,
                end_at=s + timedelta(days=1),
                open=Decimal(close),
                high=Decimal(close) + 1,
                low=Decimal(close) - 1,
                close=Decimal(close),
                volume=Decimal("1000"),
            )
        )
    return tuple(out)


@pytest.fixture(params=["memory", "sqlite"])
def cache(request: Any, tmp_path: Path) -> Any:
    if request.param == "memory":
        yield InMemoryMarketCache()
        return
    sqlite = pytest.importorskip("slaifi.infrastructure.market_data.sqlite_cache")
    c = sqlite.SqliteMarketCache(tmp_path / "market_cache.db")
    yield c
    c.close()


def test_quote_roundtrip_keeps_exact_values_and_original_times(cache: Any) -> None:
    saved = T0 + timedelta(minutes=5)
    cache.save_quote(quote(), saved_at=saved)
    loaded, saved_at = cache.load_quote(KO)
    assert loaded.price == Decimal("60.25") and loaded.previous_close == Decimal("59.5")
    assert loaded.observed_at == T0 and saved_at == saved and loaded.source == "tiingo"
    assert loaded.delayed is True and loaded.is_market_open is False
    assert loaded.change_rate == pytest.approx(0.0123)


def test_unknown_symbol_has_nothing_saved(cache: Any) -> None:
    assert cache.load_quote(AssetId("ZZZZ")) is None
    assert (
        cache.load_bars(AssetId("ZZZZ"), "1day", start_at=T0 - timedelta(days=9), end_at=T0)[0]
        == ()
    )
    assert cache.load_search("nothing") is None


def test_older_observation_does_not_replace_a_newer_one(cache: Any) -> None:
    cache.save_quote(quote("61", at=T0), saved_at=T0)
    cache.save_quote(quote("50", at=T0 - timedelta(days=2)), saved_at=T0 + timedelta(hours=1))
    assert cache.load_quote(KO)[0].price == Decimal("61")
    cache.save_quote(quote("62", at=T0 + timedelta(days=1)), saved_at=T0 + timedelta(days=1))
    assert cache.load_quote(KO)[0].price == Decimal("62")


def test_bars_roundtrip_and_are_filtered_to_the_window(cache: Any) -> None:
    cache.save_bars(KO, "1day", bars(20), source="tiingo", saved_at=T0)
    loaded, source, saved_at = cache.load_bars(
        KO,
        "1day",
        start_at=datetime(2026, 10, 5, tzinfo=UTC),
        end_at=datetime(2026, 10, 9, tzinfo=UTC),
    )
    assert source == "tiingo" and saved_at == T0
    assert [b.start_at.day for b in loaded] == [5, 6, 7, 8, 9]
    assert loaded[0].close == Decimal("60") and loaded[0].volume == Decimal("1000")


def test_saving_the_same_bars_twice_does_not_duplicate_them(cache: Any) -> None:
    for _ in range(2):
        cache.save_bars(KO, "1day", bars(10), source="fmp", saved_at=T0)
    loaded, _, _ = cache.load_bars(
        KO,
        "1day",
        start_at=datetime(2026, 9, 1, tzinfo=UTC),
        end_at=datetime(2026, 12, 1, tzinfo=UTC),
    )
    assert len(loaded) == 10


def test_bars_from_different_sources_are_never_blended(cache: Any) -> None:
    cache.save_bars(KO, "1day", bars(10, "60"), source="fmp", saved_at=T0)
    cache.save_bars(KO, "1day", bars(12, "30"), source="tiingo", saved_at=T0)  # adjusted prices
    loaded, source, _ = cache.load_bars(
        KO,
        "1day",
        start_at=datetime(2026, 9, 1, tzinfo=UTC),
        end_at=datetime(2026, 12, 1, tzinfo=UTC),
    )
    assert source == "tiingo" and len(loaded) == 12
    assert {b.close for b in loaded} == {Decimal("30")}


def test_search_roundtrip_is_case_insensitive(cache: Any) -> None:
    found = (
        InstrumentInfo(
            asset=KO, name="Coca-Cola Co", country="United States", instrument_type="Common Stock"
        ),
    )
    cache.save_search("Coca", found, source="finnhub", saved_at=T0)
    results, source, saved_at = cache.load_search("  coca ")
    assert results[0].asset.symbol == "KO" and results[0].name == "Coca-Cola Co"
    assert source == "finnhub" and saved_at == T0


def test_sqlite_cache_survives_a_restart_and_is_separate_from_the_ledger(tmp_path: Path) -> None:
    sqlite = pytest.importorskip("slaifi.infrastructure.market_data.sqlite_cache")
    path = tmp_path / "market_cache.db"
    first = sqlite.SqliteMarketCache(path)
    first.save_quote(quote("63.10"), saved_at=T0)
    first.close()
    second = sqlite.SqliteMarketCache(path)
    try:
        loaded, saved_at = second.load_quote(KO)
        assert loaded.price == Decimal("63.10") and saved_at == T0
    finally:
        second.close()
    assert path.name != "slaifi.db"
