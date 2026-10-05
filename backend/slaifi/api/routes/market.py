"""Market HTTP routes."""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from fastapi import APIRouter, Depends, Query

from slaifi.api.dependencies import get_market_history_service, get_market_overview_service
from slaifi.api.schemas.market import MarketHistoryResponse, MarketOverviewResponse
from slaifi.application.market import GetMarketHistory, GetMarketOverview
from slaifi.domain.assets import AssetClass, AssetId

router = APIRouter(prefix="/api/v1/market", tags=["market"])


@router.get("/overview", response_model=MarketOverviewResponse)
async def market_overview(service: Annotated[GetMarketOverview, Depends(get_market_overview_service)]) -> MarketOverviewResponse:
    overview = await service.execute()
    return MarketOverviewResponse.from_domain(overview)


@router.get("/history/{symbol}", response_model=MarketHistoryResponse)
async def market_history(
    symbol: str,
    service: Annotated[GetMarketHistory, Depends(get_market_history_service)],
    days: Annotated[int, Query(ge=2, le=1825)] = 93,
    asset_class: AssetClass = AssetClass.UNKNOWN,
) -> MarketHistoryResponse:
    end_at = datetime.now(UTC)
    start_at = end_at - timedelta(days=days)
    asset = AssetId(symbol=symbol, asset_class=asset_class)
    history = await service.execute(
        asset,
        start_at=start_at,
        end_at=end_at,
        interval="1day",
    )

    return MarketHistoryResponse.from_domain(history)
