"""Deterministic goal arithmetic; targets remain targets, not forecasts."""

from decimal import Decimal
from math import isfinite

from slaifi.domain.goals import (
    FeasibilityStatus,
    IncomeGoalEvaluation,
    IncomePeriod,
    IncomeTarget,
    ReturnGoalEvaluation,
    ReturnTarget,
)
from slaifi.engines.utils.errors import EngineValidationError

_PERIODS_PER_YEAR = {
    IncomePeriod.WEEKLY: Decimal("52"),
    IncomePeriod.MONTHLY: Decimal("12"),
    IncomePeriod.QUARTERLY: Decimal("4"),
    IncomePeriod.ANNUAL: Decimal("1"),
}


def annualize_income_target(target: IncomeTarget) -> Decimal:
    """Convert a periodic income target to an explicit annual requirement."""

    return target.amount * _PERIODS_PER_YEAR[target.period]


def evaluate_income_goal(
    target: IncomeTarget,
    *,
    available_capital: Decimal,
    assumed_annual_yield_rate: float | None = None,
    current_expected_annual_income: Decimal | None = None,
) -> IncomeGoalEvaluation:
    """Evaluate income arithmetic under explicitly supplied assumptions."""

    if available_capital < 0:
        raise EngineValidationError("available_capital cannot be negative")
    if (
        current_expected_annual_income is not None
        and current_expected_annual_income < 0
    ):
        raise EngineValidationError(
            "current_expected_annual_income cannot be negative"
        )
    if assumed_annual_yield_rate is not None and (
        not isfinite(assumed_annual_yield_rate)
        or assumed_annual_yield_rate < 0.0
    ):
        raise EngineValidationError(
            "assumed_annual_yield_rate must be finite and non-negative"
        )

    annual_target = annualize_income_target(target)
    required_yield = (
        float(annual_target / available_capital)
        if available_capital > 0
        else None
    )
    required_capital = None
    if (
        assumed_annual_yield_rate is not None
        and assumed_annual_yield_rate > 0.0
    ):
        required_capital = annual_target / Decimal(
            str(assumed_annual_yield_rate)
        )

    expected_income = current_expected_annual_income
    if expected_income is None and assumed_annual_yield_rate is not None:
        expected_income = available_capital * Decimal(
            str(assumed_annual_yield_rate)
        )

    if expected_income is None:
        shortfall = None
        status = FeasibilityStatus.UNDETERMINED
    else:
        shortfall = max(annual_target - expected_income, Decimal("0"))
        status = (
            FeasibilityStatus.FEASIBLE_UNDER_ASSUMPTIONS
            if expected_income >= annual_target
            else FeasibilityStatus.NOT_FEASIBLE_UNDER_ASSUMPTIONS
        )

    return IncomeGoalEvaluation(
        annual_income_target=annual_target,
        available_capital=available_capital,
        required_yield_rate=required_yield,
        assumed_annual_yield_rate=assumed_annual_yield_rate,
        required_capital_at_assumed_yield=required_capital,
        expected_annual_income=expected_income,
        annual_income_shortfall=shortfall,
        status=status,
    )


def evaluate_return_goal(
    target: ReturnTarget,
    *,
    assumed_annual_return_rate: float | None = None,
) -> ReturnGoalEvaluation:
    """Compare a target with an assumption, never a guarantee."""

    if assumed_annual_return_rate is None:
        return ReturnGoalEvaluation(
            target_annual_rate=target.annual_rate,
            assumed_annual_rate=None,
            annual_rate_gap=None,
            status=FeasibilityStatus.UNDETERMINED,
        )
    if (
        not isfinite(assumed_annual_return_rate)
        or assumed_annual_return_rate <= -1.0
    ):
        raise EngineValidationError(
            "assumed_annual_return_rate must be finite and greater than -1"
        )
    gap = assumed_annual_return_rate - target.annual_rate
    return ReturnGoalEvaluation(
        target_annual_rate=target.annual_rate,
        assumed_annual_rate=assumed_annual_return_rate,
        annual_rate_gap=gap,
        status=(
            FeasibilityStatus.FEASIBLE_UNDER_ASSUMPTIONS
            if gap >= 0.0
            else FeasibilityStatus.NOT_FEASIBLE_UNDER_ASSUMPTIONS
        ),
    )
