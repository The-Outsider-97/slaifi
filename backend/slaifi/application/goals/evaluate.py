"""Financial-goal application orchestration."""

from decimal import Decimal

from slaifi.application.contracts import FinancialReasoner, ReasoningRequest
from slaifi.application.models import GoalAnalysisResult, GoalEvaluationBundle
from slaifi.domain.goals import FinancialGoal
from slaifi.engines.goals import evaluate_income_goal, evaluate_return_goal


def evaluate_goal_bundle(
    goal: FinancialGoal,
    *,
    available_capital: Decimal,
    assumed_annual_return_rate: float | None = None,
    assumed_annual_income_yield_rate: float | None = None,
    current_expected_annual_income: Decimal | None = None,
) -> GoalEvaluationBundle:
    """Run the authoritative goal arithmetic shared by application use cases."""

    income = None
    returns = None
    if goal.income_target is not None:
        income = evaluate_income_goal(
            goal.income_target,
            available_capital=available_capital,
            assumed_annual_yield_rate=assumed_annual_income_yield_rate,
            current_expected_annual_income=current_expected_annual_income,
        )
    if goal.return_target is not None:
        returns = evaluate_return_goal(
            goal.return_target,
            assumed_annual_return_rate=assumed_annual_return_rate,
        )
    return GoalEvaluationBundle(income=income, returns=returns)


class EvaluateFinancialGoal:
    """Evaluate a goal and optionally ask SLAI to interpret the calculated result."""

    def __init__(self, reasoner: FinancialReasoner | None = None) -> None:
        self._reasoner = reasoner

    def execute(
        self,
        goal: FinancialGoal,
        *,
        available_capital: Decimal,
        assumed_annual_return_rate: float | None = None,
        assumed_annual_income_yield_rate: float | None = None,
        current_expected_annual_income: Decimal | None = None,
        reasoning_objective: str | None = None,
        request_id: str | None = None,
    ) -> GoalAnalysisResult:
        evaluation = evaluate_goal_bundle(
            goal,
            available_capital=available_capital,
            assumed_annual_return_rate=assumed_annual_return_rate,
            assumed_annual_income_yield_rate=assumed_annual_income_yield_rate,
            current_expected_annual_income=current_expected_annual_income,
        )
        result = GoalAnalysisResult(evaluation=evaluation)
        if self._reasoner is None or not reasoning_objective:
            return result

        reasoning = self._reasoner.reason(
            ReasoningRequest(
                operation="goal_evaluation",
                evidence=self._evidence(evaluation),
                objective=reasoning_objective,
                constraints=self._constraints(goal),
                assumptions={
                    "available_capital": str(available_capital),
                    "assumed_annual_return_rate": assumed_annual_return_rate,
                    "assumed_annual_income_yield_rate": assumed_annual_income_yield_rate,
                    "current_expected_annual_income": (
                        str(current_expected_annual_income)
                        if current_expected_annual_income is not None
                        else None
                    ),
                },
                uncertainty={
                    "target_is_not_guaranteed": True,
                    "prediction_model_used": False,
                },
                request_id=request_id,
            )
        )
        return GoalAnalysisResult(evaluation=evaluation, reasoning=reasoning)

    @staticmethod
    def _evidence(bundle: GoalEvaluationBundle) -> dict[str, object]:
        return {
            "income": bundle.income,
            "returns": bundle.returns,
        }

    @staticmethod
    def _constraints(goal: FinancialGoal) -> dict[str, object]:
        constraints = goal.constraints
        return {
            "max_drawdown_rate": constraints.max_drawdown_rate,
            "max_position_weight": constraints.max_position_weight,
            "max_sector_weight": constraints.max_sector_weight,
            "max_leverage": constraints.max_leverage,
            "max_short_exposure": constraints.max_short_exposure,
            "allowed_asset_classes": sorted(
                item.value for item in constraints.allowed_asset_classes
            ),
            "prohibited_asset_classes": sorted(
                item.value for item in constraints.prohibited_asset_classes
            ),
        }
