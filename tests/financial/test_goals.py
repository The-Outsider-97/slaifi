from decimal import Decimal

import pytest

from slaifi.domain.goals import (
    FeasibilityStatus,
    IncomePeriod,
    IncomeTarget,
    ReturnTarget,
)
from slaifi.engines.goals import (
    annualize_income_target,
    evaluate_income_goal,
    evaluate_return_goal,
)


def test_weekly_income_target_annualizes_with_explicit_52_factor() -> None:
    target = IncomeTarget(Decimal("150"), IncomePeriod.WEEKLY)
    assert annualize_income_target(target) == Decimal("7800")


def test_income_goal_reference_required_yield_and_capital() -> None:
    result = evaluate_income_goal(
        IncomeTarget(Decimal("150"), IncomePeriod.WEEKLY),
        available_capital=Decimal("50000"),
        assumed_annual_yield_rate=0.05,
    )
    assert result.annual_income_target == Decimal("7800")
    assert result.required_yield_rate == pytest.approx(0.156)
    assert result.required_capital_at_assumed_yield == Decimal("156000")
    assert result.expected_annual_income == Decimal("2500.00")
    assert result.annual_income_shortfall == Decimal("5300.00")
    assert result.status is FeasibilityStatus.NOT_FEASIBLE_UNDER_ASSUMPTIONS


def test_income_goal_without_assumption_is_undetermined() -> None:
    result = evaluate_income_goal(
        IncomeTarget(Decimal("100"), IncomePeriod.MONTHLY),
        available_capital=Decimal("0"),
    )
    assert result.required_yield_rate is None
    assert result.status is FeasibilityStatus.UNDETERMINED


def test_return_goal_compares_target_to_assumption() -> None:
    result = evaluate_return_goal(
        ReturnTarget(0.10),
        assumed_annual_return_rate=0.08,
    )
    assert result.annual_rate_gap == pytest.approx(-0.02)
    assert result.status is FeasibilityStatus.NOT_FEASIBLE_UNDER_ASSUMPTIONS
