import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from slaifi.application.market.get_overview import GetMarketOverview, overview_mode
from slaifi.domain.assets import AssetId
from slaifi.domain.market import FetchInfo, QuoteFetch
from slaifi.domain.market.models import AssetRef, PriceQuote

OBSERVED = datetime(2026, 9, 25, tzinfo=UTC)


def _quote(asset: AssetId, **kw: object) -> PriceQuote:
    base: dict[str, object] = dict(
        asset=asset,
        price=Decimal("123.45"),
        currency="USD",
        observed_at=OBSERVED,
        source="stub",
        change_rate=0.0125,
        delayed=False,
    )
    base.update(kw)
    return PriceQuote(**base)  # type: ignore[arg-type]


class StubGateway:
    """Returns a quote for every symbol except those listed in ``missing``."""

    def __init__(self, missing: Sequence[str] = (), **quote_kw: object) -> None:
        self.missing = set(missing)
        self.quote_kw = quote_kw

    async def fetch_quotes(self, assets: Sequence[AssetId]) -> Sequence[QuoteFetch]:
        out = []
        for asset in assets:
            if asset.symbol in self.missing:
                out.append(QuoteFetch(asset, None, FetchInfo(source=None)))
            else:
                out.append(
                    QuoteFetch(asset, _quote(asset, **self.quote_kw), FetchInfo(source="stub"))
                )
        return out


def _run(gateway: StubGateway, *symbols: str):
    service = GetMarketOverview(gateway, tuple(AssetRef(s) for s in symbols))  # type: ignore[arg-type]
    return asyncio.run(service.execute())


def test_market_overview_preserves_normalized_quotes() -> None:
    overview = _run(StubGateway(), "spy", "qqq")

    assert [quote.asset.symbol for quote in overview.quotes] == ["SPY", "QQQ"]
    assert all(quote.price == Decimal("123.45") for quote in overview.quotes)
    assert overview.generated_at.tzinfo is not None
    assert overview.unavailable == ()
    assert overview.data_mode == "live"


def test_symbols_without_any_data_are_listed_as_unavailable_not_filled_in() -> None:
    overview = _run(StubGateway(missing=["QQQ"]), "SPY", "QQQ")

    assert [q.asset.symbol for q in overview.quotes] == ["SPY"]
    assert overview.unavailable == ("QQQ",)


def test_nothing_at_all_is_unavailable() -> None:
    overview = _run(StubGateway(missing=["SPY", "QQQ"]), "SPY", "QQQ")

    assert overview.quotes == ()
    assert overview.unavailable == ("SPY", "QQQ")
    assert overview.data_mode == "unavailable"


def test_overview_mode_is_honest_about_freshness() -> None:
    spy = AssetId("SPY")
    assert overview_mode(()) == "unavailable"
    assert overview_mode((_quote(spy, delayed=False),)) == "live"
    assert overview_mode((_quote(spy, delayed=True),)) == "delayed"
    assert overview_mode((_quote(spy, delayed=None),)) == "live_delay_unknown"
    mixed = (_quote(spy, delayed=False), _quote(AssetId("QQQ"), last_known=True))
    assert overview_mode(mixed) == "last_known"


def test_overview_attaches_the_asset_class_but_never_the_exchange() -> None:
    from slaifi.domain.assets import AssetClass

    seen: list[AssetId] = []

    class Recording(StubGateway):
        async def fetch_quotes(self, assets):  # type: ignore[no-untyped-def]
            seen.extend(assets)
            return await super().fetch_quotes(assets)

    async def classify(symbol: str) -> AssetId:
        if symbol == "BAD":
            raise RuntimeError("search down")
        return AssetId(symbol, AssetClass.ETF, "NYSE", "USD")

    service = GetMarketOverview(
        Recording(),  # type: ignore[arg-type]
        (AssetRef("SPY"), AssetRef("BAD")),
        classify=classify,
    )
    asyncio.run(service.execute())
    spy, bad = seen
    assert spy.asset_class is AssetClass.ETF and spy.exchange is None and spy.currency is None
    assert bad.asset_class is AssetClass.UNKNOWN  # classification failure never blocks quotes


def test_an_instrument_that_cannot_be_classified_is_not_searched_again_on_every_load() -> None:
    from slaifi.application.market import get_overview as module
    from slaifi.domain.assets import AssetClass

    calls: list[str] = []

    async def classify(symbol: str) -> AssetId:
        calls.append(symbol)
        if symbol == "VIX":
            return AssetId(symbol)  # searched, not identified
        if symbol == "BAD":
            raise RuntimeError("search down")
        return AssetId(symbol, AssetClass.ETF)

    service = GetMarketOverview(
        StubGateway(),  # type: ignore[arg-type]
        (AssetRef("SPY"), AssetRef("VIX"), AssetRef("BAD")),
        classify=classify,
    )
    for _ in range(3):
        overview = asyncio.run(service.execute())
        assert len(overview.quotes) == 3  # quotes are never held back by classification

    # Identified symbols are asked about every time (the market service caches them itself);
    # the two unclassifiable ones are asked once, then left alone until the retry delay passes.
    assert calls.count("VIX") == 1 and calls.count("BAD") == 1 and calls.count("SPY") == 3

    for symbol in ("VIX", "BAD"):
        service._retry_at[symbol] = 0.0  # noqa: SLF001 - the retry delay has passed
    asyncio.run(service.execute())
    assert calls.count("VIX") == 2 and calls.count("BAD") == 2
    assert module.UNCLASSIFIED_RETRY_SECONDS > 0
