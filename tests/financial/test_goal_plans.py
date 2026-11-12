"""Balance and withdrawal goals: the arithmetic is checked against independent calculations."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from slaifi.domain.goals import FeasibilityStatus, GoalBasis, GoalSpec
from slaifi.domain.utils.errors import DomainValidationError
from slaifi.engines.goals.planning import (
    analyze_goal,
    future_value,
    measure_balance_progress,
    months_capital_lasts,
    required_monthly_contribution,
    solve_required_rate,
    sustainable_monthly_withdrawal,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
D = Decimal


def balance_goal(**over: object) -> GoalSpec:
    base: dict[str, object] = {
        "goal_id": "g1",
        "name": "House fund",
        "currency": "USD",
        "created_at": NOW,
        "basis": GoalBasis.TARGET_BALANCE,
        "target_value": D("20000"),
        "horizon_years": 5.0,
    }
    base.update(over)
    return GoalSpec(**base)  # type: ignore[arg-type]


def test_solved_rate_reproduces_the_target() -> None:
    rate = solve_required_rate(D("10000"), D("20000"), 5.0)
    assert rate is not None
    # Doubling in five years is 2**(1/5)-1 = 14.87% a year.
    assert rate == pytest.approx(2 ** (1 / 5) - 1, abs=1e-5)
    assert future_value(D("10000"), rate, 5.0) == pytest.approx(D("20000"), abs=D("0.5"))


def test_contributions_lower_the_required_rate() -> None:
    plain = solve_required_rate(D("10000"), D("20000"), 5.0)
    saving = solve_required_rate(D("10000"), D("20000"), 5.0, D("100"))
    assert plain is not None and saving is not None and saving < plain


def test_unreachable_target_is_none_not_a_made_up_number() -> None:
    assert solve_required_rate(D("0"), D("1000000"), 1.0) is None


def test_required_contribution_at_zero_and_positive_rates() -> None:
    # No growth: 10,000 short over 50 months is 200 a month.
    assert required_monthly_contribution(D("10000"), D("20000"), 0.0, 50 / 12) == D("200.00")
    # Already ahead of the target: nothing is required (never a negative saving).
    assert required_monthly_contribution(D("30000"), D("20000"), 0.0, 5.0) == D("0.00")
    with_growth = required_monthly_contribution(D("10000"), D("20000"), 0.05, 5.0)
    assert D("0") < with_growth < D("166.67")


def test_months_capital_lasts_matches_simple_cases() -> None:
    assert months_capital_lasts(D("1200"), 0.0, D("100"), D("0")) == 12
    # Interest alone covers the withdrawal: it never runs out within a century.
    assert months_capital_lasts(D("1000000"), 0.06, D("1000"), D("0")) is None


def test_sustainable_withdrawal_is_the_level_payment_that_ends_at_zero() -> None:
    w = sustainable_monthly_withdrawal(D("12000"), 0.0, 1.0)
    assert w == D("1000.00")
    w6 = sustainable_monthly_withdrawal(D("100000"), 0.06, 10.0)
    end = future_value(D("100000"), 0.06, 10.0, monthly_net_flow=-w6)
    assert abs(end) < D("5")


def test_balance_report_has_plan_and_findings() -> None:
    report = analyze_goal(
        balance_goal(starting_capital=D("10000"), target_value=D("25000")),
        capital=D("10000"),
        assumed_annual_return_rate=0.05,
    )
    plan = report.plan
    assert plan is not None and plan.kind == "target_balance"
    assert plan.required_annual_return_rate == pytest.approx(2.5 ** (1 / 5) - 1, abs=1e-5)
    assert plan.projected_balance is not None and plan.balance_gap is not None
    assert plan.balance_gap > 0 and plan.required_monthly_contribution is not None
    assert plan.required_monthly_contribution > 0
    assert report.status is FeasibilityStatus.NOT_FEASIBLE_UNDER_ASSUMPTIONS
    # 20% a year is above the "demanding" band, and the report says so.
    assert any(f.code == "demanding" for f in report.findings)


def test_balance_without_an_assumption_is_undetermined_and_has_no_made_up_figures() -> None:
    report = analyze_goal(balance_goal(), capital=D("10000"))
    assert report.status is FeasibilityStatus.UNDETERMINED
    assert report.plan is not None
    assert report.plan.required_monthly_contribution is None
    assert report.plan.projected_balance is None


def test_balance_with_no_capital_and_no_saving_is_flagged() -> None:
    report = analyze_goal(balance_goal(), capital=D("0"))
    codes = {f.code for f in report.findings}
    assert "no_capital" in codes and "balance_unreachable" in codes
    assert report.consistent is False


def test_replanned_report_is_labelled() -> None:
    report = analyze_goal(
        balance_goal(),
        capital=D("12000"),
        assumed_annual_return_rate=0.06,
        horizon_override=3.0,
        replanned=True,
    )
    assert report.plan is not None and report.plan.replanned_from_today
    assert report.plan.years_used == 3.0
    assert any(f.code == "replanned" for f in report.findings)


def test_withdrawal_goal_reports_how_long_money_lasts() -> None:
    spec = balance_goal(
        basis=GoalBasis.SUSTAINABLE_WITHDRAWAL,
        target_value=None,
        monthly_withdrawal=D("1000"),
        horizon_years=10.0,
    )
    report = analyze_goal(spec, capital=D("60000"), assumed_annual_return_rate=0.0)
    plan = report.plan
    assert plan is not None and plan.months_capital_lasts == 60
    assert plan.sustainable_monthly_withdrawal == D("500.00")
    assert report.status is FeasibilityStatus.NOT_FEASIBLE_UNDER_ASSUMPTIONS
    # Funding 120,000 of withdrawals from 60,000 needs growth; the report states the rate.
    assert plan.required_annual_return_rate is not None and plan.required_annual_return_rate > 0.0
    assert report.plan.lasts_beyond_100_years is False


def test_balance_progress_is_measured_against_a_straight_line() -> None:
    spec = balance_goal(starting_capital=D("10000"))
    ahead = measure_balance_progress(
        spec,
        current_value=D("16000"),
        start_value=D("10000"),
        elapsed_fraction=0.5,
        window_label="since start",
    )
    behind = measure_balance_progress(
        spec,
        current_value=D("12000"),
        start_value=D("10000"),
        elapsed_fraction=0.5,
        window_label="since start",
    )
    assert ahead is not None and ahead.on_track is True and ahead.progress_ratio == 0.8
    assert behind is not None and behind.on_track is False


def test_new_goal_kinds_validate_their_required_inputs() -> None:
    with pytest.raises(DomainValidationError):
        balance_goal(target_value=None)
    with pytest.raises(DomainValidationError):
        balance_goal(horizon_years=None)
    with pytest.raises(DomainValidationError):
        balance_goal(basis=GoalBasis.SUSTAINABLE_WITHDRAWAL, target_value=None)


def test_the_required_rate_scenario_meets_its_own_target() -> None:
    report = analyze_goal(
        balance_goal(starting_capital=D("10000")),
        capital=D("10000"),
        assumed_annual_return_rate=0.05,
    )
    own = next(s for s in report.scenarios if s.label == "Return required by the goal")
    assert own.meets_target is True and own.shortfall == D("0")
    w = balance_goal(
        basis=GoalBasis.SUSTAINABLE_WITHDRAWAL,
        target_value=None,
        monthly_withdrawal=D("1000"),
        horizon_years=10.0,
    )
    wr = analyze_goal(w, capital=D("150000"), assumed_annual_return_rate=0.04)
    assert wr.plan is not None and wr.plan.required_annual_return_rate is not None
    assert wr.plan.required_annual_return_rate < 0  # covered even with no growth
    assert any(f.code == "withdrawal_covered" for f in wr.findings)
