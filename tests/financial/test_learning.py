"""Self-measurement and adaptation rules: honest samples, no manufactured confidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from slaifi.domain.learning import (
    RecommendationOutcome,
    RecommendationRecord,
    Verdict,
    direction_of,
)
from slaifi.domain.strategies import TradingFrequency, instantiate_preset
from slaifi.engines.learning import (
    AdaptationInputs,
    GoalSignal,
    propose_adaptations,
    score_outcome,
    summarize,
    wilson_interval,
)

T0 = datetime(2026, 1, 5, tzinfo=UTC)


def record(i: int, action: str = "BUY", price: str = "100") -> RecommendationRecord:
    return RecommendationRecord(
        record_id=f"R{i}",
        symbol=f"S{i}",
        asset_class="equity",
        action=action,
        strategy_id="s",
        issued_at=T0,
        reference_price=Decimal(price),
    )


def outcome(rec: RecommendationRecord, end: str) -> RecommendationOutcome:
    return score_outcome(rec, end_price=Decimal(end), evaluated_at=T0 + timedelta(days=30))


def test_actions_map_to_a_direction() -> None:
    assert direction_of("BUY").value == "bullish"
    assert direction_of("REDUCE").value == "bearish"
    assert direction_of("HOLD").value == "neutral"


def test_scoring_bullish_bearish_flat_and_neutral() -> None:
    assert outcome(record(1, "BUY"), "110").correct is True
    assert outcome(record(2, "BUY"), "90").correct is False
    assert outcome(record(3, "SELL"), "90").correct is True
    assert outcome(record(4, "SELL"), "110").correct is False
    # Inside the 0.5% flat band nothing is a hit or a miss.
    assert outcome(record(5, "BUY"), "100.3").correct is None
    # HOLD makes no price call, however far the price moved.
    assert outcome(record(6, "HOLD"), "150").correct is None


def test_wilson_interval_is_sane() -> None:
    assert wilson_interval(0, 0) is None
    low, high = wilson_interval(10, 20) or (0, 0)
    assert low < 0.5 < high
    low, high = wilson_interval(20, 20) or (0, 0)
    assert low > 0.8 and high == pytest.approx(1.0, abs=1e-9)


def _history(
    hits: int, misses: int
) -> list[tuple[RecommendationRecord, RecommendationOutcome | None]]:
    rows: list[tuple[RecommendationRecord, RecommendationOutcome | None]] = []
    for i in range(hits):
        r = record(i)
        rows.append((r, outcome(r, "110")))
    for i in range(hits, hits + misses):
        r = record(i)
        rows.append((r, outcome(r, "90")))
    return rows


def test_small_samples_get_no_verdict_even_if_they_look_perfect() -> None:
    summary = summarize(_history(hits=8, misses=0))
    assert summary.hit_rate == 1.0 and summary.scored == 8
    assert summary.verdict is Verdict.INSUFFICIENT_SAMPLE
    assert "at least 20" in summary.note


def test_verdicts_need_the_interval_to_clear_chance() -> None:
    assert summarize(_history(24, 6)).verdict is Verdict.BETTER_THAN_CHANCE
    assert summarize(_history(6, 24)).verdict is Verdict.WORSE_THAN_CHANCE
    assert summarize(_history(13, 12)).verdict is Verdict.NO_CLEAR_EDGE


def test_pending_and_neutral_calls_are_counted_but_not_scored() -> None:
    pending = record(100)
    flat = record(101, "HOLD")
    summary = summarize([(pending, None), (flat, outcome(flat, "130"))] + _history(2, 1))
    assert summary.logged == 5 and summary.pending == 1 and summary.scored == 3


def strategy(**over: object):  # type: ignore[no-untyped-def]
    from dataclasses import replace

    return replace(instantiate_preset("short_term_balanced", strategy_id="x"), **over)


def test_drawdown_near_limit_proposes_only_tightening() -> None:
    s = strategy()  # drawdown limit 15%, position cap 15%, cash reserve 10%
    report = propose_adaptations(
        AdaptationInputs(strategy=s, valuation_points=30, max_drawdown=-0.13)
    )
    near = next(p for p in report.proposals if p.code == "drawdown_near_limit")
    assert near.kind == "tighten" and near.change is not None
    assert near.change["max_position_weight"] < 0.15
    assert near.change["cash_reserve_rate"] > 0.10
    assert any("13.0%" in e for e in near.evidence)


def test_no_history_means_no_behaviour_rules_and_says_so() -> None:
    report = propose_adaptations(
        AdaptationInputs(strategy=strategy(), valuation_points=3, max_drawdown=-0.5)
    )
    assert not report.proposals
    assert any("at least 10" in n for n in report.notes)


def test_safe_portfolio_gets_no_suggestions() -> None:
    report = propose_adaptations(
        AdaptationInputs(strategy=strategy(), valuation_points=40, max_drawdown=-0.02)
    )
    assert report.proposals == ()


def test_underperforming_signals_suggest_less_trading_only_with_enough_data() -> None:
    s = strategy(trading_frequency=TradingFrequency.HIGH)
    weak = summarize(_history(6, 24))
    report = propose_adaptations(AdaptationInputs(strategy=s, track_record=weak))
    change = next(p.change for p in report.proposals if p.code == "signals_underperformed")
    assert change == {"trading_frequency": "medium"}
    thin = summarize(_history(1, 4))
    assert not propose_adaptations(AdaptationInputs(strategy=s, track_record=thin)).proposals


def test_goal_rules_align_income_and_never_suggest_more_risk() -> None:
    s = strategy(income_weight=0.0)
    cons = instantiate_preset("capital_preservation", strategy_id="c")
    goals = [
        GoalSignal("dividends", "investment_income"),
        GoalSignal("moonshot", "total_return", required_annual_return_rate=0.30),
        GoalSignal("house", "target_balance", behind_pace=True),
    ]
    a = propose_adaptations(AdaptationInputs(strategy=s, goals=goals))
    assert next(p for p in a.proposals if p.code == "income_goal_without_income_tilt").change == {
        "income_weight": 0.5
    }
    assert any(p.code == "goal_behind_pace" for p in a.proposals)
    b = propose_adaptations(AdaptationInputs(strategy=cons, goals=goals))
    risk = next(p for p in b.proposals if p.code == "goal_needs_more_risk")
    assert risk.kind == "observation" and risk.change is None
    # No rule ever proposes a looser limit or a bigger risk setting.
    for p in (*a.proposals, *b.proposals):
        assert not (p.change and ("risk_tolerance" in p.change))
