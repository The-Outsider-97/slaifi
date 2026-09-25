"""Financial-goal HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from slaifi.api.dependencies import get_goal_evaluation_service, get_request_id
from slaifi.api.schemas.goals import EvaluateGoalRequest, GoalAnalysisResponse
from slaifi.application.goals import EvaluateFinancialGoal

router = APIRouter(prefix="/api/v1/goals", tags=["goals"])


@router.post("/evaluate", response_model=GoalAnalysisResponse)
def evaluate_goal(
    payload: EvaluateGoalRequest,
    service: Annotated[EvaluateFinancialGoal, Depends(get_goal_evaluation_service)],
    request_id: Annotated[str | None, Depends(get_request_id)],
) -> GoalAnalysisResponse:
    result = service.execute(
        payload.goal.to_domain(),
        available_capital=payload.available_capital,
        assumed_annual_return_rate=payload.assumed_annual_return_rate,
        assumed_annual_income_yield_rate=payload.assumed_annual_income_yield_rate,
        current_expected_annual_income=payload.current_expected_annual_income,
        reasoning_objective=payload.reasoning_objective,
        request_id=request_id,
    )
    return GoalAnalysisResponse.from_application(result)
