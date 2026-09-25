"""Market HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from slaifi.api.dependencies import get_market_overview_service
from slaifi.api.schemas.market import MarketOverviewResponse
from slaifi.application.market.get_overview import GetMarketOverview

router = APIRouter(prefix="/api/v1/market", tags=["market"])


@router.get("/overview", response_model=MarketOverviewResponse)
async def market_overview(
    service: Annotated[GetMarketOverview, Depends(get_market_overview_service)],
) -> MarketOverviewResponse:
    """Return the normalized Home dashboard market overview."""

    overview = await service.execute()
    return MarketOverviewResponse.from_domain(overview)
