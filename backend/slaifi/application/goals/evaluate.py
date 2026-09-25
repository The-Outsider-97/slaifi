"""Standalone goal-feasibility application service."""

from decimal import Decimal

from slaifi.application.models import GoalEvaluationBundle
from slaifi.domain.goals import FinancialGoal
from slaifi.engines.goals import evaluate_income_goal, evaluate_return_goal


class EvaluateFinancialGoal:
    def execute(
        self,
        goal: FinancialGoal,
        *,
        available_capital: Decimal,
        assumed_annual_return_rate: float | None = None,
        assumed_annual_income_yield_rate: float | None = None,
        current_expected_annual_income: Decimal | None = None,
    ) -> GoalEvaluationBundle:
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
