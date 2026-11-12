"""Suggested strategy adjustments from how a paper portfolio actually behaved.

Rules, not a learned model. Every suggestion names the measured evidence it rests on, and the
rules only ever suggest *tightening* limits or aligning a preference with a stated goal. Taking
more risk is never suggested: that stays a deliberate choice the person makes. Nothing is
applied here; a suggestion is data for the person (or the advisor's confirmation flow) to act on.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from slaifi.domain.learning import TrackRecord, Verdict
from slaifi.domain.strategies import StrategyProfile, TradingFrequency

MIN_VALUATION_POINTS = 10
NEAR_LIMIT_SHARE = 0.80  # act when the realised drawdown has used 80% of the allowed one
POSITION_TIGHTEN_FACTOR = 0.75
RESERVE_STEP = 0.05
RESERVE_CEILING = 0.50
DEMANDING_GOAL_RATE = 0.15

_FREQUENCY_DOWN = {
    TradingFrequency.HIGH: TradingFrequency.MEDIUM,
    TradingFrequency.MEDIUM: TradingFrequency.LOW,
}


@dataclass(frozen=True, slots=True)
class GoalSignal:
    name: str
    basis: str
    required_annual_return_rate: float | None = None
    behind_pace: bool | None = None


@dataclass(frozen=True, slots=True)
class AdaptationInputs:
    strategy: StrategyProfile
    valuation_points: int = 0
    max_drawdown: float | None = None  # as measured: zero or negative
    largest_position_weight: float | None = None
    cash_weight: float | None = None
    track_record: TrackRecord | None = None
    goals: Sequence[GoalSignal] = ()


@dataclass(frozen=True, slots=True)
class AdaptationProposal:
    code: str
    kind: str  # tighten | align | observation
    title: str
    rationale: str
    evidence: tuple[str, ...]
    # Field changes in the strategy-update vocabulary; ``None`` for observations.
    change: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class AdaptationReport:
    proposals: tuple[AdaptationProposal, ...]
    notes: tuple[str, ...] = field(default_factory=tuple)


def _pct(value: float) -> str:
    return f"{value:.1%}"


def propose_adaptations(inputs: AdaptationInputs) -> AdaptationReport:
    strategy = inputs.strategy
    proposals: list[AdaptationProposal] = []
    notes: list[str] = [
        "Suggestions come from simple rules over measured results. They never raise risk, "
        "and nothing changes until you apply it."
    ]

    if inputs.valuation_points < MIN_VALUATION_POINTS:
        notes.append(
            f"The portfolio has {inputs.valuation_points} recorded valuation point(s); "
            f"portfolio-behaviour rules need at least {MIN_VALUATION_POINTS}, so none were applied."
        )
    else:
        limit = strategy.max_drawdown_rate
        if limit is not None and inputs.max_drawdown is not None:
            realised = -inputs.max_drawdown
            if realised >= NEAR_LIMIT_SHARE * limit:
                change: dict[str, Any] = {}
                position_cap = strategy.max_position_weight
                if position_cap is not None and position_cap > 0.03:
                    change["max_position_weight"] = round(position_cap * POSITION_TIGHTEN_FACTOR, 2)
                reserve = min(strategy.cash_reserve_rate + RESERVE_STEP, RESERVE_CEILING)
                if reserve > strategy.cash_reserve_rate:
                    change["cash_reserve_rate"] = round(reserve, 2)
                over = realised >= limit
                if change:
                    proposals.append(
                        AdaptationProposal(
                            code="drawdown_over_limit" if over else "drawdown_near_limit",
                            kind="tighten",
                            title="Cut the size of single positions and hold more cash",
                            rationale=(
                                "The paper portfolio's worst fall has "
                                + ("passed" if over else "used most of")
                                + " the drawdown you allowed, so smaller positions and a larger "
                                "cash cushion would leave more room."
                            ),
                            evidence=(
                                f"Worst fall so far: {_pct(realised)}",
                                f"Your drawdown limit: {_pct(limit)}",
                            ),
                            change=change,
                        )
                    )
        weight = inputs.largest_position_weight
        cap = strategy.max_position_weight
        if weight is not None and cap is not None and weight > cap + 0.02:
            proposals.append(
                AdaptationProposal(
                    code="position_above_cap",
                    kind="observation",
                    title="One holding has grown past your position limit",
                    rationale=(
                        "Prices moved it above the cap. The strategy itself is fine; consider "
                        "trimming that holding."
                    ),
                    evidence=(f"Largest position: {_pct(weight)}", f"Your cap: {_pct(cap)}"),
                )
            )
        cash = inputs.cash_weight
        if cash is not None and cash < strategy.cash_reserve_rate - 0.02:
            proposals.append(
                AdaptationProposal(
                    code="cash_below_reserve",
                    kind="observation",
                    title="Cash is below your reserve",
                    rationale="You are invested more heavily than the reserve you set allows.",
                    evidence=(
                        f"Cash now: {_pct(cash)}",
                        f"Reserve you set: {_pct(strategy.cash_reserve_rate)}",
                    ),
                )
            )

    record = inputs.track_record
    if (
        record is not None
        and record.verdict is Verdict.WORSE_THAN_CHANCE
        and strategy.trading_frequency in _FREQUENCY_DOWN
    ):
        lower = _FREQUENCY_DOWN[strategy.trading_frequency]
        proposals.append(
            AdaptationProposal(
                code="signals_underperformed",
                kind="tighten",
                title="Trade less often",
                rationale=(
                    "Recommendations have not beaten a coin flip over a large enough sample, so "
                    "acting on fewer of them cuts costs and noise."
                ),
                evidence=(
                    f"Decisive results: {record.scored}",
                    f"Hit rate: {_pct(record.hit_rate or 0.0)}"
                    + (
                        f" (95% range {_pct(record.interval_low or 0.0)}–"
                        f"{_pct(record.interval_high or 0.0)})"
                    ),
                ),
                change={"trading_frequency": lower.value},
            )
        )

    for goal in inputs.goals:
        if goal.basis == "investment_income" and strategy.income_weight < 0.3:
            proposals.append(
                AdaptationProposal(
                    code="income_goal_without_income_tilt",
                    kind="align",
                    title="Lean towards income",
                    rationale=(
                        f"“{goal.name}” counts dividends and interest, but the strategy puts "
                        "little weight on income."
                    ),
                    evidence=(f"Income focus now: {_pct(strategy.income_weight)}",),
                    change={"income_weight": 0.5},
                )
            )
        rate = goal.required_annual_return_rate
        if (
            rate is not None
            and rate >= DEMANDING_GOAL_RATE
            and strategy.risk_tolerance.value == "conservative"
        ):
            proposals.append(
                AdaptationProposal(
                    code="goal_needs_more_risk",
                    kind="observation",
                    title="A goal and your risk level disagree",
                    rationale=(
                        f"“{goal.name}” needs about {_pct(rate)} a year, more than a conservative "
                        "strategy is built for. SLAIFI will not suggest taking more risk; "
                        "lowering the target, adding savings or giving it more time are the "
                        "alternatives."
                    ),
                    evidence=(f"Return the goal needs: {_pct(rate)} a year",),
                )
            )
        if goal.behind_pace:
            proposals.append(
                AdaptationProposal(
                    code="goal_behind_pace",
                    kind="observation",
                    title="A goal is behind its straight-line pace",
                    rationale=(
                        f"“{goal.name}” is behind pace. Analyse it with a portfolio attached to "
                        "see what it would take from today."
                    ),
                    evidence=("Measured progress is below a straight line to the target",),
                )
            )
    return AdaptationReport(tuple(proposals), tuple(notes))
