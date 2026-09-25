"""Financial-analysis HTTP routes."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from slaifi.api.dependencies import (
    get_market_analysis_service,
    get_portfolio_analysis_service,
    get_request_id,
    get_runtime_settings,
)
from slaifi.api.schemas.analysis import (
    MarketAnalysisRequest,
    MarketAnalysisResponse,
    PortfolioAnalysisRequest,
    PortfolioAnalysisResponse,
)
from slaifi.application.analysis import AnalyzeMarketSeries, AnalyzePortfolio
from slaifi.core.config import Settings
from slaifi.core.exceptions import ValidationError
from slaifi.domain.assets import AssetId

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


@router.post("/market", response_model=MarketAnalysisResponse)
def analyze_market(
    payload: MarketAnalysisRequest,
    service: Annotated[AnalyzeMarketSeries, Depends(get_market_analysis_service)],
    settings: Annotated[Settings, Depends(get_runtime_settings)],
    request_id: Annotated[str | None, Depends(get_request_id)],
) -> MarketAnalysisResponse:
    if len(payload.bars) > settings.api_max_market_bars:
        raise HTTPException(
            status_code=413,
            detail=f"market analysis accepts at most {settings.api_max_market_bars} bars",
        )
    asset = payload.asset.to_domain()
    bars = tuple(item.to_domain(asset) for item in payload.bars)
    result = service.execute(
        asset,
        bars,
        periods_per_year=payload.periods_per_year,
        moving_average_period=payload.moving_average_period,
        momentum_period=payload.momentum_period,
        rsi_period=payload.rsi_period,
        atr_period=payload.atr_period,
        reasoning_objective=payload.reasoning_objective,
        request_id=request_id,
    )
    return MarketAnalysisResponse.from_application(result)


@router.post("/portfolio", response_model=PortfolioAnalysisResponse)
def analyze_portfolio(
    payload: PortfolioAnalysisRequest,
    service: Annotated[AnalyzePortfolio, Depends(get_portfolio_analysis_service)],
    settings: Annotated[Settings, Depends(get_runtime_settings)],
    request_id: Annotated[str | None, Depends(get_request_id)],
) -> PortfolioAnalysisResponse:
    if len(payload.portfolio.trades) > settings.api_max_portfolio_trades:
        raise HTTPException(
            status_code=413,
            detail=(
                "portfolio analysis accepts at most "
                f"{settings.api_max_portfolio_trades} trades"
            ),
        )
    portfolio = payload.portfolio.to_domain()
    prices: dict[AssetId, Decimal] = {}
    for item in payload.prices:
        asset = item.asset.to_domain()
        if asset in prices:
            raise ValidationError(f"duplicate price for {asset.display_symbol}")
        prices[asset] = item.price

    result = service.execute(
        portfolio,
        prices,
        as_of=payload.as_of,
        initial_cash=payload.initial_cash,
        returns=payload.returns,
        equity_values=payload.equity_values,
        periods_per_year=payload.periods_per_year,
        risk_free_annual_rate=payload.risk_free_annual_rate,
        goal=payload.goal.to_domain() if payload.goal is not None else None,
        assumed_annual_return_rate=payload.assumed_annual_return_rate,
        assumed_annual_income_yield_rate=payload.assumed_annual_income_yield_rate,
        current_expected_annual_income=payload.current_expected_annual_income,
        reasoning_objective=payload.reasoning_objective,
        request_id=request_id,
    )
    return PortfolioAnalysisResponse.from_application(result)
