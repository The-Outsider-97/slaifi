"""Strategy and goal-tracker routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from slaifi.api import serializers as out
from slaifi.api.dependencies import get_goal_tracker, get_strategy_service
from slaifi.api.schemas.finance import GoalAnalyze, GoalCreate, StrategyCreate, StrategyUpdate
from slaifi.api.security import MutationGuard
from slaifi.application.goals import GoalTracker
from slaifi.application.strategies import StrategyService

router = APIRouter(prefix="/api/v1", tags=["strategies-and-goals"])
Strategies = Annotated[StrategyService, Depends(get_strategy_service)]
Goals = Annotated[GoalTracker, Depends(get_goal_tracker)]


@router.get("/strategies")
async def list_strategies(svc: Strategies) -> dict[str, Any]:
    return {
        "active_strategy_id": svc.active_id(),
        "strategies": [out.strategy(s) for s in svc.list()],
        "presets": [out.strategy(s) for s in svc.presets()],
        "note": "Presets only initialise a strategy. Every value can be edited afterwards.",
    }


@router.post("/strategies", dependencies=[MutationGuard], status_code=201)
async def create_strategy(body: StrategyCreate, svc: Strategies) -> dict[str, Any]:
    return out.strategy(
        svc.create(
            name=body.name, preset_id=body.preset_id, fields=body.fields, activate=body.activate
        )
    )


@router.get("/strategies/{strategy_id}")
async def get_strategy(strategy_id: str, svc: Strategies) -> dict[str, Any]:
    return out.strategy(svc.get(strategy_id))


@router.patch("/strategies/{strategy_id}", dependencies=[MutationGuard])
async def update_strategy(
    strategy_id: str, body: StrategyUpdate, svc: Strategies
) -> dict[str, Any]:
    return out.strategy(
        svc.update(strategy_id, body.fields, acknowledge_loosening=body.acknowledge_loosening)
    )


@router.post("/strategies/{strategy_id}/activate", dependencies=[MutationGuard])
async def activate_strategy(strategy_id: str, svc: Strategies) -> dict[str, Any]:
    return out.strategy(svc.activate(strategy_id))


@router.delete("/strategies/{strategy_id}", dependencies=[MutationGuard])
async def delete_strategy(strategy_id: str, svc: Strategies) -> dict[str, Any]:
    svc.delete(strategy_id)
    return {"deleted": strategy_id}


@router.get("/goal-tracker")
async def list_goals(goals: Goals) -> dict[str, Any]:
    return {"goals": [out.goal(g) for g in goals.list()]}


@router.post("/goal-tracker", dependencies=[MutationGuard], status_code=201)
async def create_goal(body: GoalCreate, goals: Goals) -> dict[str, Any]:
    fields = body.model_dump(exclude_none=True)
    return out.goal(goals.create(fields))


@router.delete("/goal-tracker/{goal_id}", dependencies=[MutationGuard])
async def delete_goal(goal_id: str, goals: Goals) -> dict[str, Any]:
    goals.delete(goal_id)
    return {"deleted": goal_id}


@router.post("/goal-tracker/{goal_id}/analyze")
async def analyze_goal(goal_id: str, body: GoalAnalyze, goals: Goals) -> dict[str, Any]:
    report = await goals.analyze(
        goal_id,
        assumed_annual_return_rate=body.assumed_annual_return_rate,
        portfolio_id=body.portfolio_id,
    )
    return out.goal_report(report)
