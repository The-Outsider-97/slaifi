"""Self-measurement and adaptation: track record, strategy suggestions, SLAI goal review."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from slaifi.api import serializers as out
from slaifi.api.dependencies import get_learning_service
from slaifi.api.schemas.finance import GoalAnalyze
from slaifi.api.security import MutationGuard
from slaifi.application.learning import LearningService

router = APIRouter(prefix="/api/v1", tags=["learning"])
Learning = Annotated[LearningService, Depends(get_learning_service)]


@router.get("/learning/track-record")
async def track_record(svc: Learning) -> dict[str, Any]:
    return out.track_record(svc.track_record())


@router.post("/learning/track-record/refresh", dependencies=[MutationGuard])
async def refresh_track_record(svc: Learning) -> dict[str, Any]:
    """Check due recommendations against real prices (one data request per symbol, capped)."""

    result = await svc.refresh_outcomes()
    return {
        "refresh": out.refresh_result(result),
        "track_record": out.track_record(svc.track_record()),
    }


@router.get("/strategies/{strategy_id}/adaptations")
async def strategy_adaptations(
    strategy_id: str,
    svc: Learning,
    portfolio_id: str | None = None,
    explain: bool = False,
) -> dict[str, Any]:
    return out.adaptation(
        await svc.adaptations(strategy_id, portfolio_id=portfolio_id, explain=explain)
    )


@router.post("/goal-tracker/{goal_id}/review")
async def review_goal(goal_id: str, body: GoalAnalyze, svc: Learning) -> dict[str, Any]:
    """The goal's deterministic report plus SLAI's plain-language reading of it."""

    return out.goal_review(
        await svc.review_goal(
            goal_id,
            assumed_annual_return_rate=body.assumed_annual_return_rate,
            portfolio_id=body.portfolio_id,
        )
    )
