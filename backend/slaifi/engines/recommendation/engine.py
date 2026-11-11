"""Assemble an auditable :class:`RecommendationReport` from validated market evidence."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from statistics import stdev

from slaifi.domain.assets import AssetId
from slaifi.domain.market import OHLCVBar
from slaifi.domain.portfolio import PortfolioSnapshot
from slaifi.domain.predictions import Prediction, PredictionInterval, UncertaintyMeasure
from slaifi.domain.recommendations import (
    ConstraintFinding,
    ModelVersion,
    PredictionValidation,
    RecommendationAction,
    RecommendationReport,
    ReportStatus,
    SignalDirection,
    SignalReading,
)
from slaifi.domain.strategies import StrategyProfile
from slaifi.engines.prediction import (
    MODEL_NAME,
    MODEL_VERSION,
    NOMINAL_COVERAGE,
    estimate_interval,
    horizon_bars_for_days,
    horizon_returns,
    validate_walk_forward,
)
from slaifi.engines.recommendation.rules import (
    ELIGIBILITY_CODES,
    choose_action,
    risk_level_from_volatility,
    thresholds_for,
)
from slaifi.engines.recommendation.signals import (
    MIN_BARS_FOR_SIGNALS,
    aggregate_score,
    build_frame,
    readings_at,
)
from slaifi.engines.risk import maximum_drawdown
from slaifi.engines.strategy import asset_eligibility, check_buy
from slaifi.engines.technical import assess_bars, normalize_bars

RULES_MODEL = ModelVersion("slaifi_signal_rules", "1.0.0")
_TRADING_DAYS = 252
_MAX_BAR_AGE = {
    "1day": timedelta(days=7),
    "1week": timedelta(days=21),
    "1month": timedelta(days=75),
}


@dataclass(frozen=True, slots=True)
class RecommendationInputs:
    bars: Sequence[OHLCVBar]
    strategy: StrategyProfile
    generated_at: datetime
    interval: str = "1day"
    data_mode: str = "unknown"
    illustrative: bool = False
    snapshot: PortfolioSnapshot | None = None
    portfolio_drawdown: float | None = None


def _insufficient(
    inputs: RecommendationInputs,
    reasons: list[str],
    *,
    signals: tuple[SignalReading, ...] = (),
    last_bar_at: datetime | None = None,
    count: int = 0,
    findings: tuple[ConstraintFinding, ...] = (),
    asset: AssetId,
    holding_qty: str | None = None,
) -> RecommendationReport:
    return RecommendationReport(
        asset=asset,
        generated_at=inputs.generated_at,
        horizon_days=inputs.strategy.horizon_days,
        strategy_id=inputs.strategy.strategy_id,
        status=ReportStatus.INSUFFICIENT_EVIDENCE,
        action=None,
        signal_score=None,
        risk_level=None,
        signals=signals,
        constraint_findings=findings,
        insufficient_reasons=tuple(reasons),
        observation_count=count,
        last_bar_at=last_bar_at,
        data_mode=inputs.data_mode,
        illustrative=inputs.illustrative,
        position_quantity=holding_qty,
        model_versions=(RULES_MODEL,),
        summary="Insufficient evidence: " + " ".join(reasons),
    )


def _volatility(closes: Sequence[float]) -> float | None:
    window = list(closes[-(_TRADING_DAYS + 1) :])
    if len(window) < 21:
        return None
    returns = [b / a - 1.0 for a, b in zip(window, window[1:], strict=False)]
    return float(stdev(returns) * (_TRADING_DAYS**0.5))


def build_report(inputs: RecommendationInputs) -> RecommendationReport:  # noqa: C901
    strategy = inputs.strategy
    bars, _, _ = normalize_bars(list(inputs.bars))
    if not bars:
        raise ValueError("build_report requires at least one bar to identify the asset")
    asset = bars[0].asset
    closes = [float(bar.close) for bar in bars]
    holding_qty = None
    holding = False
    if inputs.snapshot is not None:
        for valuation in inputs.snapshot.positions:
            if valuation.position.asset == asset and valuation.position.quantity > 0:
                holding = True
                holding_qty = str(valuation.position.quantity)

    reasons: list[str] = []
    quality = assess_bars(bars, inputs.interval)
    if inputs.illustrative:
        reasons.append(
            "The price history is illustrative (synthetic) data, which cannot support a "
            "recommendation."
        )
    if len(bars) < MIN_BARS_FOR_SIGNALS:
        reasons.append(
            f"Only {len(bars)} bars are available; at least {MIN_BARS_FOR_SIGNALS} are needed."
        )
    max_age = _MAX_BAR_AGE.get(inputs.interval)
    if max_age is not None and inputs.generated_at - bars[-1].end_at > max_age:
        reasons.append(
            f"The latest bar ({bars[-1].end_at:%Y-%m-%d}) is too old to describe current conditions."
        )
    if quality.gap_count > 0 and quality.largest_gap_days and quality.largest_gap_days > 20:
        reasons.append(
            f"The history has an unexplained gap of {quality.largest_gap_days:.0f} days."
        )

    vol = _volatility(closes) if len(closes) >= 22 else None
    findings = list(asset_eligibility(asset, strategy, annualized_volatility=vol))

    if len(bars) < MIN_BARS_FOR_SIGNALS:
        return _insufficient(
            inputs,
            reasons,
            last_bar_at=bars[-1].end_at,
            count=len(bars),
            findings=tuple(findings),
            asset=asset,
            holding_qty=holding_qty,
        )

    frame = build_frame(closes)
    last = len(frame) - 1
    readings = readings_at(frame, last)
    score, coverage = aggregate_score(readings)
    thresholds = thresholds_for(strategy)
    if score is None or coverage < thresholds.min_weight_coverage:
        reasons.append("Too few indicators could be computed to form a view.")
    if reasons:
        return _insufficient(
            inputs,
            reasons,
            signals=readings,
            last_bar_at=bars[-1].end_at,
            count=len(bars),
            findings=tuple(findings),
            asset=asset,
            holding_qty=holding_qty,
        )
    assert score is not None

    # --- constraint context -----------------------------------------------------------------
    purchase_findings: list[ConstraintFinding] = []
    if inputs.snapshot is not None:
        purchase_findings = [
            f
            for f in check_buy(
                inputs.snapshot,
                asset,
                trade_value=Decimal("0"),
                fee=Decimal("0"),
                strategy=strategy,
                annualized_volatility=vol,
                portfolio_drawdown=inputs.portfolio_drawdown,
            )
            if f.code not in {x.code for x in findings}
        ]
    findings.extend(purchase_findings)
    eligibility_blocked = any(
        f.severity == "hard" and f.code in ELIGIBILITY_CODES for f in findings
    )
    purchase_blocked = any(f.severity == "hard" for f in purchase_findings)
    action, reason = choose_action(
        score,
        strategy=strategy,
        holding=holding,
        eligibility_blocked=eligibility_blocked,
        purchase_blocked=purchase_blocked,
    )

    # --- supporting / conflicting ---------------------------------------------------------------
    bullish = [r for r in readings if r.direction is SignalDirection.BULLISH]
    bearish = [r for r in readings if r.direction is SignalDirection.BEARISH]
    leaning_up = score >= 0
    supporting = [r.rationale for r in (bullish if leaning_up else bearish)]
    conflicting = [r.rationale for r in (bearish if leaning_up else bullish)]
    conflicting.extend(f.message for f in findings if f.severity == "hard")

    # --- invalidation conditions -------------------------------------------------------------------
    invalidation: list[str] = []
    slow = frame.sma_slow[last]
    if slow is not None:
        if action in {
            RecommendationAction.BUY,
            RecommendationAction.DCA,
            RecommendationAction.HOLD,
        }:
            invalidation.append(f"A daily close below the 50-bar average ({slow:.2f}).")
        elif action in {
            RecommendationAction.SELL,
            RecommendationAction.REDUCE,
            RecommendationAction.AVOID,
        }:
            invalidation.append(f"A daily close back above the 50-bar average ({slow:.2f}).")
        else:
            invalidation.append(
                f"A sustained move through the 50-bar average ({slow:.2f}) would change the view."
            )
    if frame.rsi[last] is not None and leaning_up:
        invalidation.append("RSI rising above 70 while momentum fades.")
    invalidation.append(
        f"The score moving across {thresholds.buy:+.2f} / {thresholds.sell:+.2f} "
        "re-triggers a different action."
    )

    # --- validated prediction (or none) -------------------------------------------------------------
    prediction = None
    validation = None
    notes: list[str] = []
    expected_downside = None
    if inputs.interval == "1day":
        horizon = horizon_bars_for_days(strategy.horizon_days)
        if horizon * 2 + 120 < len(closes):
            check = validate_walk_forward(closes, horizon)
            validation = PredictionValidation(
                method="walk_forward_empirical_quantile",
                nominal_coverage=check.nominal_coverage,
                realized_coverage=check.realized_coverage,
                test_count=check.test_count,
                mean_interval_width=check.mean_interval_width,
                passed=check.passed,
                note=check.note,
            )
            if check.passed:
                estimate = estimate_interval(
                    horizon_returns(closes, horizon), nominal_coverage=NOMINAL_COVERAGE
                )
                prediction = Prediction(
                    asset=asset,
                    horizon=timedelta(days=strategy.horizon_days),
                    generated_at=inputs.generated_at,
                    input_data_at=min(bars[-1].end_at, inputs.generated_at),
                    model_name=MODEL_NAME,
                    model_version=MODEL_VERSION,
                    expected_return_rate=estimate.median,
                    interval=PredictionInterval(
                        estimate.lower, estimate.upper, coverage_probability=NOMINAL_COVERAGE
                    ),
                    uncertainty=UncertaintyMeasure(
                        "interval_width", estimate.upper - estimate.lower, "return_rate"
                    ),
                )
                expected_downside = max(0.0, -estimate.lower)
                notes.append(
                    "The interval is the historical range of this asset's horizon returns "
                    "(median shown as its centre). It is validated out of sample on this "
                    "history only and may fail when market conditions change."
                )
            else:
                notes.append("No forecast released: " + check.note)
        else:
            notes.append(
                "No forecast released: the history is too short to validate an interval "
                f"for a {strategy.horizon_days}-day horizon."
            )
    else:
        notes.append("Forecast intervals are only produced for daily bars.")

    risk_level = risk_level_from_volatility(vol)
    if vol is not None:
        notes.append(f"Trailing realised volatility is {vol:.1%} annualised (252 bars/year).")
    drawdown = maximum_drawdown(closes[-(_TRADING_DAYS + 1) :]) if len(closes) > 1 else None
    if drawdown is not None:
        notes.append(f"Maximum drawdown over the last year of bars is {drawdown:.1%}.")
    summary = (
        f"{action.value}: {reason} Rule score {score:+.2f} on a −1…+1 scale "
        f"(not a probability); {len(bars)} bars through {bars[-1].end_at:%Y-%m-%d}."
    )
    return RecommendationReport(
        asset=asset,
        generated_at=inputs.generated_at,
        horizon_days=strategy.horizon_days,
        strategy_id=strategy.strategy_id,
        status=ReportStatus.RECOMMENDATION,
        action=action,
        signal_score=score,
        risk_level=risk_level,
        signals=readings,
        supporting_signals=tuple(supporting),
        conflicting_signals=tuple(conflicting),
        invalidation_conditions=tuple(invalidation),
        constraint_findings=tuple(findings),
        prediction=prediction,
        prediction_validation=validation,
        expected_downside_rate=expected_downside,
        observation_count=len(bars),
        last_bar_at=bars[-1].end_at,
        data_mode=inputs.data_mode,
        illustrative=inputs.illustrative,
        position_quantity=holding_qty,
        model_versions=(RULES_MODEL, ModelVersion(MODEL_NAME, MODEL_VERSION))
        if prediction
        else (RULES_MODEL,),
        summary=summary,
        notes=tuple(notes),
    )
