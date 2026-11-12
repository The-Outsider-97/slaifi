"""Feasibility analysis and progress measurement for persisted goals.

Everything here is arithmetic over *explicit* inputs. A target is an objective, never a
forecast: scenarios are labelled by where their rate came from (user assumption, hypothetical
grid, or measured portfolio history) and nothing is presented as an expected return.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
from math import isfinite

from slaifi.domain.goals import (
    FeasibilityStatus,
    GoalBasis,
    GoalFeasibilityReport,
    GoalFinding,
    GoalProgress,
    GoalScenario,
    GoalSpec,
    IncomePeriod,
    IncomeTarget,
)
from slaifi.engines.goals.evaluation import annualize_income_target
from slaifi.engines.utils.errors import EngineValidationError

_CENT = Decimal("0.01")
_ZERO = Decimal("0")
# Hypothetical return grid. These are *not* forecasts; they show sensitivity only.
HYPOTHETICAL_ANNUAL_RATES: tuple[float, ...] = (0.0, 0.04, 0.08, 0.12)
HYPOTHETICAL_STRESS_LOSS_RATE = 0.20
# Heuristic bands used only to phrase warnings; stated in docs/finance/goals-model.md.
DEMANDING_REQUIRED_RATE = 0.15
VERY_DEMANDING_REQUIRED_RATE = 0.30
MODERATE_RISK_REQUIRED_RATE = 0.10


def _q(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _dec(value: float) -> Decimal:
    return Decimal(repr(value))


def future_value(
    capital: Decimal,
    annual_rate: float,
    years: float,
    *,
    monthly_net_flow: Decimal = _ZERO,
) -> Decimal:
    """Monthly-compounded future value with end-of-month net contributions.

    ``annual_rate`` is a compound annual rate; the monthly rate is its exact equivalent.
    """

    if not isfinite(annual_rate) or annual_rate <= -1.0:
        raise EngineValidationError("annual_rate must be finite and greater than -1")
    if not isfinite(years) or years <= 0.0:
        raise EngineValidationError("years must be positive")
    months = round(years * 12)
    if months < 1:
        raise EngineValidationError("horizon is shorter than one month")
    monthly_rate = (1.0 + annual_rate) ** (1.0 / 12.0) - 1.0
    growth = (Decimal(1) + _dec(monthly_rate)) ** months
    value = capital * growth
    if monthly_net_flow != 0:
        if monthly_rate == 0.0:
            value += monthly_net_flow * months
        else:
            value += monthly_net_flow * (growth - 1) / _dec(monthly_rate)
    return _q(value)


def required_annual_amount(spec: GoalSpec) -> Decimal | None:
    if spec.target_amount is None or spec.period is None:
        return None
    return annualize_income_target(IncomeTarget(spec.target_amount, spec.period))


def _period_years(period: IncomePeriod) -> float:
    return {
        IncomePeriod.DAILY: 1 / 252,
        IncomePeriod.WEEKLY: 1 / 52,
        IncomePeriod.MONTHLY: 1 / 12,
        IncomePeriod.QUARTERLY: 1 / 4,
        IncomePeriod.ANNUAL: 1.0,
    }[period]


def analyze_goal(
    spec: GoalSpec,
    *,
    capital: Decimal,
    assumed_annual_return_rate: float | None = None,
    measured_annual_return_rate: float | None = None,
    portfolio_max_drawdown: float | None = None,
    strategy_max_drawdown_rate: float | None = None,
    strategy_risk_tolerance: str | None = None,
    progress: GoalProgress | None = None,
) -> GoalFeasibilityReport:
    """Evaluate consistency, required return/cash flow, risk conflicts and scenarios."""

    if capital < 0:
        raise EngineValidationError("capital cannot be negative")
    findings: list[GoalFinding] = []
    assumptions: list[str] = [
        "Targets are objectives, not guarantees or forecasts.",
        f"Capital used for the arithmetic: {capital:.2f} {spec.currency}.",
        "Required rates ignore taxes and assume costs are already inside the stated return.",
    ]
    annual_target = required_annual_amount(spec)
    risk_tolerance = spec.risk_tolerance or strategy_risk_tolerance
    drawdown_limit = spec.max_acceptable_drawdown_rate or strategy_max_drawdown_rate

    # --- required return / required capital --------------------------------------------------
    required_rate: float | None
    if annual_target is not None:
        required_rate = float(annual_target / capital) if capital > 0 else None
        if capital == 0:
            findings.append(
                GoalFinding(
                    "no_capital",
                    "critical",
                    "There is no capital to evaluate the goal against; "
                    "a positive starting amount is needed.",
                )
            )
        assumptions.append(
            f"Per-{spec.period.value if spec.period else 'period'} target annualised using "
            f"{'252 trading days' if spec.period is IncomePeriod.DAILY else 'calendar periods'}."
        )
    else:
        required_rate = spec.target_annual_rate

    if spec.target_annual_rate is not None and annual_target is not None:
        required_rate = max(required_rate or 0.0, spec.target_annual_rate)
        findings.append(
            GoalFinding(
                "two_targets",
                "info",
                "The goal has both an amount target and a rate target; the more demanding "
                "required rate is used.",
            )
        )

    # --- scenarios ---------------------------------------------------------------------------
    scenario_rates: list[tuple[str, float, str]] = []
    if assumed_annual_return_rate is not None:
        scenario_rates.append(
            ("Your assumed return", assumed_annual_return_rate, "user_assumption")
        )
    if measured_annual_return_rate is not None:
        scenario_rates.append(
            ("Measured paper-portfolio return", measured_annual_return_rate, "historical_portfolio")
        )
    if required_rate is not None and isfinite(required_rate) and required_rate > -1.0:
        scenario_rates.append(("Return required by the goal", required_rate, "hypothetical"))
    for rate in HYPOTHETICAL_ANNUAL_RATES:
        scenario_rates.append((f"Hypothetical {rate:.0%} per year", rate, "hypothetical"))

    horizon = spec.horizon_years
    net_flow = spec.monthly_contribution - spec.monthly_withdrawal
    stress_rate = drawdown_limit if drawdown_limit is not None else HYPOTHETICAL_STRESS_LOSS_RATE
    stress_loss = _q(capital * _dec(stress_rate))
    scenarios: list[GoalScenario] = []
    seen: set[float] = set()
    for label, rate, source in scenario_rates:
        key = round(rate, 6)
        if key in seen:
            continue
        seen.add(key)
        projected = None
        if horizon is not None and capital >= 0:
            try:
                projected = future_value(capital, rate, horizon, monthly_net_flow=net_flow)
            except EngineValidationError:
                projected = None
        period_profit = None
        shortfall = None
        meets = False
        if annual_target is not None:
            annual_profit = _q(capital * _dec(rate))
            period_profit = _q(annual_profit * Decimal(str(_period_years(spec.period))))  # type: ignore[arg-type]
            shortfall = max(_q(annual_target - annual_profit), _ZERO)
            meets = annual_profit >= annual_target
        elif spec.target_annual_rate is not None:
            meets = rate >= spec.target_annual_rate
        scenarios.append(
            GoalScenario(
                label=label,
                annual_return_rate=rate,
                source=source,
                projected_value=projected,
                period_profit=period_profit,
                shortfall=shortfall,
                meets_target=meets,
                stress_loss=stress_loss,
            )
        )

    # --- required capital at the assumed rate -------------------------------------------------
    required_capital = None
    if annual_target is not None and assumed_annual_return_rate and assumed_annual_return_rate > 0:
        required_capital = _q(annual_target / _dec(assumed_annual_return_rate))

    # --- consistency & risk conflict findings -------------------------------------------------
    if required_rate is not None and isfinite(required_rate):
        if required_rate >= VERY_DEMANDING_REQUIRED_RATE:
            findings.append(
                GoalFinding(
                    "very_demanding",
                    "critical",
                    f"Reaching this goal from {capital:.2f} needs about {required_rate:.1%} per "
                    "year. A sustained return at that level is very demanding and is "
                    "aspirational rather than a reasonable planning assumption.",
                )
            )
        elif required_rate >= DEMANDING_REQUIRED_RATE:
            findings.append(
                GoalFinding(
                    "demanding",
                    "warning",
                    f"The goal needs about {required_rate:.1%} per year, which is demanding "
                    "and usually means accepting substantial volatility and drawdowns.",
                )
            )
        if required_rate > MODERATE_RISK_REQUIRED_RATE:
            if risk_tolerance == "conservative":
                findings.append(
                    GoalFinding(
                        "risk_conflict",
                        "critical",
                        f"A required return of {required_rate:.1%} per year conflicts with a "
                        "conservative risk tolerance. Either lower the target, add capital or "
                        "contributions, lengthen the horizon, or accept more risk deliberately.",
                    )
                )
            if drawdown_limit is not None and drawdown_limit <= 0.10:
                findings.append(
                    GoalFinding(
                        "drawdown_conflict",
                        "warning",
                        f"A drawdown limit of {drawdown_limit:.0%} leaves little room to pursue "
                        f"a {required_rate:.1%} annual requirement.",
                    )
                )
    if annual_target is not None and spec.monthly_withdrawal > 0:
        yearly_withdrawal = spec.monthly_withdrawal * 12
        findings.append(
            GoalFinding(
                "withdrawals",
                "info",
                f"Planned withdrawals of {yearly_withdrawal:.2f} per year reduce the capital "
                "that has to earn the target.",
            )
        )
    if (
        spec.target_annual_rate is not None
        and spec.target_annual_rate <= 0.0
        and spec.monthly_withdrawal > 0
    ):
        findings.append(
            GoalFinding(
                "preservation_with_withdrawals",
                "warning",
                "Capital preservation while withdrawing means returns must at least cover the "
                "withdrawals; check the withdrawal rate against your assumed return.",
            )
        )
    if horizon is None and spec.target_annual_rate is not None and annual_target is None:
        findings.append(
            GoalFinding(
                "no_horizon",
                "info",
                "No horizon was given, so projected values are not computed.",
            )
        )
    if assumed_annual_return_rate is None and measured_annual_return_rate is None:
        findings.append(
            GoalFinding(
                "no_assumption",
                "info",
                "No return assumption was supplied: feasibility is undetermined. "
                "The scenario table shows what each hypothetical rate would imply.",
            )
        )
    if (
        portfolio_max_drawdown is not None
        and drawdown_limit is not None
        and -portfolio_max_drawdown > drawdown_limit
    ):
        findings.append(
            GoalFinding(
                "drawdown_breached",
                "critical",
                f"The paper portfolio's drawdown ({-portfolio_max_drawdown:.1%}) exceeds "
                f"the {drawdown_limit:.0%} limit attached to this goal.",
            )
        )

    # --- status ---------------------------------------------------------------------------------
    reference_rate = (
        assumed_annual_return_rate
        if assumed_annual_return_rate is not None
        else measured_annual_return_rate
    )
    if reference_rate is None or required_rate is None:
        status = FeasibilityStatus.UNDETERMINED
    else:
        status = (
            FeasibilityStatus.FEASIBLE_UNDER_ASSUMPTIONS
            if reference_rate >= required_rate
            else FeasibilityStatus.NOT_FEASIBLE_UNDER_ASSUMPTIONS
        )
    if reference_rate is not None and measured_annual_return_rate is not None:
        assumptions.append(
            "A measured paper-portfolio return is a historical observation of one short "
            "track record; it does not predict future returns."
        )
    consistent = not any(f.severity == "critical" for f in findings)
    return GoalFeasibilityReport(
        goal_id=spec.goal_id,
        consistent=consistent,
        status=status,
        capital_used=_q(capital),
        annual_target_amount=annual_target,
        required_annual_return_rate=required_rate,
        required_capital_at_assumed_rate=required_capital,
        assumed_annual_return_rate=reference_rate,
        scenarios=tuple(scenarios),
        findings=tuple(findings),
        assumptions=tuple(assumptions),
        progress=progress,
    )


def measure_progress(
    spec: GoalSpec,
    *,
    measured_amount: Decimal,
    window_label: str,
    elapsed_fraction: float,
) -> GoalProgress:
    """Measured progress for an amount-per-period goal inside the current period window."""

    if not 0.0 <= elapsed_fraction <= 1.0:
        raise EngineValidationError("elapsed_fraction must be in [0, 1]")
    target = spec.target_amount
    if target is None:
        return GoalProgress(
            basis=spec.basis,
            window_label=window_label,
            measured_amount=_q(measured_amount),
            target_amount=None,
            progress_ratio=None,
            on_track=None,
            detail="This goal has a rate target, so period progress is not measured here.",
        )
    ratio = float(measured_amount / target)
    pro_rata = target * Decimal(str(elapsed_fraction))
    on_track = measured_amount >= pro_rata
    detail = (
        f"Measured {measured_amount:.2f} of {target:.2f} {spec.currency} "
        f"({window_label}); a straight-line pace would be {pro_rata:.2f} by now. "
        "Pace is a comparison, not a prediction."
    )
    return GoalProgress(
        basis=spec.basis,
        window_label=window_label,
        measured_amount=_q(measured_amount),
        target_amount=target,
        progress_ratio=ratio,
        on_track=on_track,
        detail=detail,
    )


def annualize_measured_return(
    start_value: Decimal,
    end_value: Decimal,
    elapsed_days: float,
    *,
    minimum_days: int = 90,
) -> float | None:
    """Compound annualisation of a *measured* return; refuses short windows (returns None)."""

    if start_value <= 0 or end_value <= 0 or elapsed_days < minimum_days:
        return None
    return float((end_value / start_value) ** (Decimal(365) / Decimal(str(elapsed_days))) - 1)


def basis_labels() -> Sequence[str]:
    return tuple(basis.value for basis in GoalBasis)
