"""Financial-goal HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from slaifi.api.dependencies import get_goal_evaluation_service
from slaifi.api.schemas.goals import EvaluateGoalRequest, GoalEvaluationResponse
from slaifi.application.goals import EvaluateFinancialGoal

router = APIRouter(prefix="/api/v1/goals", tags=["goals"])


@router.post("/evaluate", response_model=GoalEvaluationResponse)
def evaluate_goal(
    payload: EvaluateGoalRequest,
    service: Annotated[EvaluateFinancialGoal, Depends(get_goal_evaluation_service)],
) -> GoalEvaluationResponse:
    result = service.execute(
        payload.goal.to_domain(),
        available_capital=payload.available_capital,
        assumed_annual_return_rate=payload.assumed_annual_return_rate,
        assumed_annual_income_yield_rate=payload.assumed_annual_income_yield_rate,
        current_expected_annual_income=payload.current_expected_annual_income,
    )
    return GoalEvaluationResponse.from_application(result)
