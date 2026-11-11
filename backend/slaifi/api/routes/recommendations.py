"""Rule-based recommendations and historical simulations."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from slaifi.api import serializers as out
from slaifi.api.dependencies import get_recommendation_service
from slaifi.application.recommendations import RecommendationService

router = APIRouter(prefix="/api/v1/recommendations", tags=["recommendations"])
Svc = Annotated[RecommendationService, Depends(get_recommendation_service)]


@router.get("/{symbol}")
async def recommend(
    symbol: str,
    svc: Svc,
    strategy_id: str | None = None,
    portfolio_id: str | None = None,
    explain: bool = False,
    days: int = Query(730, ge=30, le=3650),
) -> dict[str, Any]:
    return out.recommendation(
        await svc.recommend(
            symbol, strategy_id=strategy_id, portfolio_id=portfolio_id, explain=explain, days=days
        )
    )


@router.get("/{symbol}/backtest")
async def backtest(
    symbol: str,
    svc: Svc,
    strategy_id: str | None = None,
    days: int = Query(1095, ge=30, le=3650),
) -> dict[str, Any]:
    return out.backtest(await svc.backtest(symbol, strategy_id=strategy_id, days=days))
