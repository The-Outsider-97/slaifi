"""Recommendation, prediction-validation and back-test behaviour on synthetic bars."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from slaifi.core.types import CurrencyCode
from slaifi.domain.assets import AssetClass, AssetId
from slaifi.domain.market import OHLCVBar
from slaifi.domain.recommendations import ReportStatus
from slaifi.domain.strategies import DEFAULT_PRESET_ID, PRESET_IDS, instantiate_preset
from slaifi.engines.backtest import run_backtest
from slaifi.engines.recommendation import RecommendationInputs, build_report
from slaifi.engines.utils.errors import InsufficientDataError

ASSET = AssetId("TEST", AssetClass.EQUITY, "NYSE", CurrencyCode("USD"))
ALLOWED_ACTIONS = {"BUY", "HOLD", "SELL", "WATCH", "AVOID", "REDUCE", "DCA"}


def make_bars(
    count: int, drift: float = 0.0004, vol: float = 0.01, start: float = 100.0, seed: int = 7
) -> list[OHLCVBar]:
    bars: list[OHLCVBar] = []
    price = start
    t0 = datetime(2023, 1, 2, tzinfo=UTC)
    state = seed
    for i in range(count):
        state = (state * 1103515245 + 12345) % (2**31)
        shock = ((state / 2**31) - 0.5) * 2 * vol * 1.7
        price *= math.exp(drift + shock)
        o, c = price / (1 + shock / 2), price
        hi, lo = max(o, c) * 1.004, min(o, c) * 0.996
        s = t0 + timedelta(days=i)
        bars.append(
            OHLCVBar(
                ASSET,
                s,
                s + timedelta(days=1),
                Decimal(f"{o:.4f}"),
                Decimal(f"{hi:.4f}"),
                Decimal(f"{lo:.4f}"),
                Decimal(f"{c:.4f}"),
                Decimal(1000 + i),
            )
        )
    return bars


def strategy(preset: str = DEFAULT_PRESET_ID):
    return instantiate_preset(preset, strategy_id="s", name="s")


def inputs(
    bars: list[OHLCVBar], last_known: bool = False, mode: str = "retrieved"
) -> RecommendationInputs:
    return RecommendationInputs(
        bars=bars,
        strategy=strategy(),
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        data_mode=mode,
        last_known=last_known,
    )


def test_last_known_data_never_produces_a_recommendation() -> None:
    report = build_report(inputs(make_bars(600), last_known=True, mode="last_known"))
    assert report.status is ReportStatus.INSUFFICIENT_EVIDENCE
    assert report.action is None
    assert report.signal_score is None
    assert report.prediction is None
    assert report.insufficient_reasons


def test_too_little_history_is_insufficient_evidence() -> None:
    report = build_report(inputs(make_bars(30)))
    assert report.status is ReportStatus.INSUFFICIENT_EVIDENCE
    assert report.action is None


@pytest.mark.parametrize("preset", PRESET_IDS)
def test_recommendation_uses_only_allowed_actions_and_bounded_score(preset: str) -> None:
    report = build_report(
        RecommendationInputs(
            bars=make_bars(600),
            strategy=strategy(preset),
            generated_at=datetime(2026, 1, 1, tzinfo=UTC),
            data_mode="retrieved",
            last_known=False,
        )
    )
    if report.status is ReportStatus.RECOMMENDATION:
        assert report.action is not None and report.action.value in ALLOWED_ACTIONS
        assert report.signal_score is not None and -1.0 <= report.signal_score <= 1.0
        assert report.signals and report.invalidation_conditions
        assert report.model_versions
    else:
        assert report.action is None


def test_prediction_is_only_present_when_walk_forward_validation_passed() -> None:
    report = build_report(inputs(make_bars(900)))
    if report.prediction is not None:
        assert report.prediction_validation is not None and report.prediction_validation.passed
        assert report.prediction.interval is not None
        assert (
            report.prediction.interval.lower_return_rate
            <= report.prediction.interval.upper_return_rate
        )
        assert report.prediction_validation.test_count >= 20
    # A report never exposes probability, confidence or accuracy fields.
    fields = {f for f in vars(report)} if hasattr(report, "__dict__") else set(report.__slots__)
    assert not {"probability", "confidence", "accuracy", "expected_return"} & fields


def test_backtest_requires_enough_history() -> None:
    with pytest.raises(InsufficientDataError):
        run_backtest(make_bars(60), strategy())


def test_backtest_reports_costs_and_a_buy_and_hold_benchmark() -> None:
    result = run_backtest(make_bars(700), strategy())
    assert result.benchmark_total_return is not None
    assert result.assumptions
    assert result.commission_rate is not None and result.slippage_rate is not None
    assert 0.0 <= (result.exposure_rate or 0.0) <= 1.0


def test_backtest_has_no_look_ahead() -> None:
    """Changing only future prices must not change any trade that closed before the change."""

    bars = make_bars(700)
    cut = 600
    changed = bars[:cut] + [
        OHLCVBar(
            b.asset, b.start_at, b.end_at, b.open * 3, b.high * 3, b.low * 3, b.close * 3, b.volume
        )
        for b in bars[cut:]
    ]
    base = run_backtest(bars, strategy())
    other = run_backtest(changed, strategy())
    boundary = bars[cut].start_at
    early_a = [t for t in base.trades if t.exited_at is not None and t.exited_at < boundary]
    early_b = [t for t in other.trades if t.exited_at is not None and t.exited_at < boundary]
    assert early_a == early_b
    assert len(base.trades) >= 1
