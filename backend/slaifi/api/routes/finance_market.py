"""Market search, quotes, series, statistics, comparison, watchlist and screening routes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from slaifi.api import serializers as out
from slaifi.api.dependencies import (
    get_finance_store,
    get_market_data_service,
    get_recommendation_service,
)
from slaifi.api.schemas.finance import ScreenRequest, WatchlistAdd
from slaifi.api.security import MutationGuard
from slaifi.application.contracts import FinanceStore
from slaifi.application.market import MarketDataService
from slaifi.application.recommendations import RecommendationService
from slaifi.core.utils.errors import ValidationError
from slaifi.domain.assets import AssetClass
from slaifi.domain.ledger import WatchlistItem

router = APIRouter(prefix="/api/v1/market", tags=["market"])

Market = Annotated[MarketDataService, Depends(get_market_data_service)]
Store = Annotated[FinanceStore, Depends(get_finance_store)]

# Chart ranges map to a number of calendar days.
RANGES: dict[str, int] = {"1D": 1, "5D": 5, "1M": 31, "3M": 93, "6M": 186, "1Y": 366, "5Y": 1830}
OVERLAY_NAMES = ("sma20", "sma50", "rsi14")


def _days(range_: str | None, days: int | None) -> int:
    if days is not None:
        return days
    if range_ is None:
        return 186
    try:
        return RANGES[range_.upper()]
    except KeyError as exc:
        raise ValidationError(f"range must be one of {', '.join(RANGES)}") from exc


@router.get("/search")
async def search(
    market: Market,
    q: Annotated[str, Query(min_length=1, max_length=64)],
    limit: int = Query(10, ge=1, le=25),
) -> dict[str, Any]:
    return out.search(await market.search(q, limit=limit))


@router.get("/meta")
async def meta(market: Market) -> dict[str, Any]:
    """What the chart controls may offer, and what kind of data is being served."""

    return {
        "intervals": list(market.supported_intervals),
        "ranges": list(RANGES),
        "overlays": list(OVERLAY_NAMES),
        "data_mode": market.data_mode,
        "provenance": out.provenance(market.provenance()),
    }


@router.get("/quote/{symbol}")
async def quote(symbol: str, market: Market, exchange: str | None = None) -> dict[str, Any]:
    asset = await market.resolve_asset(symbol, exchange=exchange)
    view = await market.quote(asset)
    if view is None:
        raise ValidationError(f"no quote is available for {asset.symbol} right now")
    return out.quote(view)


@router.get("/series/{symbol}")
async def series(
    symbol: str,
    market: Market,
    interval: str = "1day",
    range: str | None = None,  # noqa: A002 - public query parameter name
    days: int | None = Query(None, ge=1, le=3650),
    overlays: str | None = None,
    exchange: str | None = None,
) -> dict[str, Any]:
    names = tuple(n.strip() for n in (overlays or "").split(",") if n.strip())
    bad = [n for n in names if n not in OVERLAY_NAMES]
    if bad:
        raise ValidationError(f"unknown overlay {', '.join(bad)}; use {', '.join(OVERLAY_NAMES)}")
    asset = await market.resolve_asset(symbol, exchange=exchange)
    view = await market.history(asset, days=_days(range, days), interval=interval, overlays=names)
    return out.series(view)


@router.get("/stats/{symbol}")
async def stats(
    symbol: str,
    market: Market,
    interval: str = "1day",
    range: str | None = None,  # noqa: A002
    days: int | None = Query(None, ge=1, le=3650),
    exchange: str | None = None,
) -> dict[str, Any]:
    asset = await market.resolve_asset(symbol, exchange=exchange)
    return out.stats(await market.stats(asset, days=_days(range or "1Y", days), interval=interval))


@router.get("/compare")
async def compare(
    market: Market,
    symbols: Annotated[str, Query(min_length=1, max_length=200)],
    interval: str = "1day",
    range: str | None = None,  # noqa: A002
    days: int | None = Query(None, ge=1, le=3650),
) -> dict[str, Any]:
    names = [s.strip() for s in symbols.split(",") if s.strip()]
    assets = [await market.resolve_asset(n) for n in names]
    return out.comparison(
        await market.compare(assets, days=_days(range or "1Y", days), interval=interval)
    )


@router.get("/watchlist")
async def watchlist(store: Store, market: Market) -> dict[str, Any]:
    items = list(store.list_watchlist())
    quotes = {}
    if items:
        try:
            for view in await market.quotes([i.asset for i in items]):
                quotes[view.quote.asset.symbol] = view
        except Exception:  # noqa: BLE001 - a quote outage must not hide the user's own list
            quotes = {}
    return {
        "items": [out.watchlist_item(i, quotes.get(i.asset.symbol)) for i in items],
        "provenance": out.provenance(market.provenance()),
    }


@router.post("/watchlist", dependencies=[MutationGuard], status_code=201)
async def watchlist_add(body: WatchlistAdd, store: Store, market: Market) -> dict[str, Any]:
    asset = await market.resolve_asset(body.symbol, exchange=body.exchange)
    name = None
    found = await market.search(asset.symbol, limit=5)
    for hit in found.results:
        if hit.asset.symbol == asset.symbol:
            name = hit.name
            break
    store.add_watchlist(WatchlistItem(asset=asset, name=name, added_at=datetime.now(UTC)))
    return {"added": out.asset(asset), "name": name}


@router.delete("/watchlist/{symbol}", dependencies=[MutationGuard])
async def watchlist_remove(
    symbol: str, store: Store, exchange: str | None = None
) -> dict[str, Any]:
    removed = store.remove_watchlist(symbol.strip().upper(), exchange.upper() if exchange else None)
    return {"removed": removed}


@router.post("/screen")
async def screen(
    body: ScreenRequest, svc: Annotated[RecommendationService, Depends(get_recommendation_service)]
) -> dict[str, Any]:
    views = await svc.screen(
        body.symbols, strategy_id=body.strategy_id, portfolio_id=body.portfolio_id
    )
    return {"results": [out.recommendation(v) for v in views]}


# Keep the import referenced for type checkers when AssetClass filtering is added.
_ = AssetClass
