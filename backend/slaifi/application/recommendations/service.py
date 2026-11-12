"""Recommendation use case: deterministic engine first, SLAI interpretation second."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from slaifi.application.advisor.guards import guard_interpretation
from slaifi.application.contracts import (
    FinancialReasoner,
    NullSafetyReviewer,
    ReasoningRequest,
    ReasoningStatus,
    ReasoningUnavailableError,
    SafetyReview,
    SafetyReviewer,
)
from slaifi.application.market import DataProvenance, MarketDataService
from slaifi.application.paper import PaperTradingService
from slaifi.application.strategies import StrategyService
from slaifi.core.utils.errors import SlaifiError, ValidationError
from slaifi.domain.assets import AssetClass
from slaifi.domain.portfolio import PortfolioSnapshot
from slaifi.domain.recommendations import RecommendationReport, ReportStatus
from slaifi.domain.strategies import StrategyProfile
from slaifi.engines.backtest import BacktestResult, run_backtest
from slaifi.engines.recommendation import RecommendationInputs, build_report
from slaifi.engines.utils.errors import InsufficientDataError

DEFAULT_HISTORY_DAYS = 1825
MAX_SCREEN_SYMBOLS = 12


@dataclass(frozen=True, slots=True)
class Explanation:
    """SLAI's interpretation of a deterministic report. It never changes the report."""

    status: str  # available | degraded | unavailable | disabled | withheld | not_requested
    text: str | None
    agent: str | None = None
    validation_status: str | None = None
    warnings: tuple[str, ...] = ()
    safety: SafetyReview | None = None


@dataclass(frozen=True, slots=True)
class RecommendationView:
    report: RecommendationReport
    provenance: DataProvenance
    strategy: StrategyProfile
    explanation: Explanation | None
    history_notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BacktestView:
    symbol: str
    result: BacktestResult | None
    provenance: DataProvenance
    strategy: StrategyProfile
    message: str | None = None


def report_evidence(report: RecommendationReport) -> dict[str, Any]:
    """JSON-safe evidence envelope handed to SLAI (authoritative values only)."""

    return {
        "asset": report.asset.display_symbol,
        "asset_class": report.asset.asset_class.value,
        "status": report.status.value,
        "action": report.action.value if report.action else None,
        "rule_score": report.signal_score,
        "score_scale": "−1 (bearish) … +1 (bullish); a rule aggregate, not a probability",
        "risk_level": report.risk_level.value if report.risk_level else None,
        "horizon_days": report.horizon_days,
        "signals": [
            {
                "name": s.name,
                "value": s.value,
                "direction": s.direction.value,
                "rationale": s.rationale,
            }
            for s in report.signals
        ],
        "supporting_signals": list(report.supporting_signals),
        "conflicting_signals": list(report.conflicting_signals),
        "invalidation_conditions": list(report.invalidation_conditions),
        "constraint_findings": [
            {"code": f.code, "severity": f.severity, "message": f.message}
            for f in report.constraint_findings
        ],
        "prediction": (
            {
                "model": f"{report.prediction.model_name} {report.prediction.model_version}",
                "horizon_days": report.prediction.horizon.days,
                "interval_lower_return": report.prediction.interval.lower_return_rate
                if report.prediction.interval
                else None,
                "interval_upper_return": report.prediction.interval.upper_return_rate
                if report.prediction.interval
                else None,
                "median_historical_return": report.prediction.expected_return_rate,
            }
            if report.prediction
            else None
        ),
        "prediction_validation": report.prediction_validation.note
        if report.prediction_validation
        else None,
        "observations": report.observation_count,
        "data_mode": report.data_mode,
        "last_known_data": report.last_known,
        "notes": list(report.notes),
    }


class RecommendationService:
    def __init__(
        self,
        market: MarketDataService,
        strategies: StrategyService,
        paper: PaperTradingService,
        *,
        reasoner: FinancialReasoner | None = None,
        safety: SafetyReviewer | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._market = market
        self._strategies = strategies
        self._paper = paper
        self._reasoner = reasoner
        self._safety = safety or NullSafetyReviewer()
        self._clock = clock or (lambda: datetime.now(UTC))

    async def _snapshot(
        self, portfolio_id: str | None
    ) -> tuple[PortfolioSnapshot | None, float | None]:
        if portfolio_id is None:
            return None, None
        view = await self._paper.view(portfolio_id, record=False)
        return view.snapshot, self._paper.drawdown(portfolio_id)

    async def recommend(
        self,
        symbol: str,
        *,
        strategy_id: str | None = None,
        portfolio_id: str | None = None,
        explain: bool = False,
        exchange: str | None = None,
        asset_class: AssetClass | None = None,
        days: int = DEFAULT_HISTORY_DAYS,
    ) -> RecommendationView:
        strategy = self._strategies.resolve(strategy_id)
        asset = await self._market.resolve_asset(symbol, exchange=exchange, asset_class=asset_class)
        history = await self._market.history(asset, days=days, interval="1day")
        snapshot, drawdown = await self._snapshot(portfolio_id)
        now = self._clock()
        if not history.bars:
            from slaifi.domain.recommendations import ModelVersion

            report = RecommendationReport(
                asset=asset,
                generated_at=now,
                horizon_days=strategy.horizon_days,
                strategy_id=strategy.strategy_id,
                status=ReportStatus.INSUFFICIENT_EVIDENCE,
                action=None,
                signal_score=None,
                risk_level=None,
                insufficient_reasons=(
                    "NOT AVAILABLE: no historical data could be retrieved for this instrument.",
                ),
                data_mode=history.provenance.mode,
                last_known=history.provenance.last_known,
                model_versions=(ModelVersion("slaifi_signal_rules", "1.0.0"),),
                summary="Insufficient evidence: no historical data is available for this instrument.",
            )
        else:
            report = build_report(
                RecommendationInputs(
                    bars=history.bars,
                    strategy=strategy,
                    generated_at=now,
                    interval="1day",
                    data_mode=history.provenance.mode,
                    last_known=history.provenance.last_known,
                    snapshot=snapshot,
                    portfolio_drawdown=drawdown,
                )
            )
        explanation = await self._explain(report, strategy) if explain else None
        return RecommendationView(report, history.provenance, strategy, explanation, history.notes)

    async def screen(
        self,
        symbols: Sequence[str],
        *,
        strategy_id: str | None = None,
        portfolio_id: str | None = None,
    ) -> list[RecommendationView]:
        unique = list(dict.fromkeys(s.strip().upper() for s in symbols if s.strip()))
        if not unique:
            raise ValidationError("provide at least one symbol")
        if len(unique) > MAX_SCREEN_SYMBOLS:
            raise ValidationError(f"screen at most {MAX_SCREEN_SYMBOLS} symbols at once")
        results = await asyncio.gather(
            *(
                self.recommend(s, strategy_id=strategy_id, portfolio_id=portfolio_id)
                for s in unique
            ),
            return_exceptions=True,
        )
        views: list[RecommendationView] = []
        for item in results:
            if isinstance(item, RecommendationView):
                views.append(item)
            elif isinstance(item, SlaifiError) and not isinstance(item, ValidationError):
                continue  # an unknown or unavailable symbol is simply omitted from the screen
            elif isinstance(item, BaseException):
                raise item
        return views

    async def backtest(
        self, symbol: str, *, strategy_id: str | None = None, days: int = DEFAULT_HISTORY_DAYS
    ) -> BacktestView:
        strategy = self._strategies.resolve(strategy_id)
        asset = await self._market.resolve_asset(symbol)
        history = await self._market.history(asset, days=days, interval="1day")
        try:
            result: BacktestResult | None = run_backtest(history.bars, strategy)
            message = None
        except InsufficientDataError as exc:
            result, message = None, exc.message
        if history.provenance.last_known:
            message = (
                message + " " if message else ""
            ) + "This simulation used last-known history because live sources could not be reached."
        return BacktestView(asset.symbol, result, history.provenance, strategy, message)

    async def _explain(
        self, report: RecommendationReport, strategy: StrategyProfile
    ) -> Explanation:
        if report.status is not ReportStatus.RECOMMENDATION:
            return Explanation(
                "not_requested", None, warnings=("There is no recommendation to interpret.",)
            )
        if self._reasoner is None:
            return Explanation("disabled", None, warnings=("SLAI reasoning is not configured.",))
        evidence = report_evidence(report)
        request = ReasoningRequest(
            operation="recommendation_explanation",
            evidence=evidence,
            objective=(
                f"Explain in plain language why SLAIFI's deterministic engine produced "
                f"{report.action.value if report.action else 'no action'} for {report.asset.display_symbol} "
                "under the active strategy, weighing the supporting and conflicting signals and the "
                "strategy limits. Do not change the action, add price targets, probabilities, confidence "
                "figures or personal advice."
            ),
            constraints={
                "authoritative_action": report.action.value if report.action else None,
                "strategy_horizon_days": strategy.horizon_days,
                "risk_tolerance": strategy.risk_tolerance.value,
                "hard_limits_override_signals": True,
            },
            assumptions={"data_mode": report.data_mode},
            uncertainty={"prediction_validated": report.prediction is not None},
        )
        return await self.run_reasoner(request, purpose="recommendation_explanation")

    async def run_reasoner(self, request: ReasoningRequest, *, purpose: str) -> Explanation:
        assert self._reasoner is not None
        try:
            result = await asyncio.to_thread(self._reasoner.reason, request)
        except ReasoningUnavailableError as exc:
            return Explanation("unavailable", None, warnings=(str(exc),))
        except Exception as exc:  # noqa: BLE001 - SLAI is optional; deterministic output stands alone
            return Explanation(
                "unavailable", None, warnings=(f"SLAI reasoning failed ({type(exc).__name__}).",)
            )
        warnings = list(result.warnings)
        if (
            result.status in {ReasoningStatus.UNAVAILABLE, ReasoningStatus.DISABLED}
            or not result.interpretation
        ):
            return Explanation(
                result.status.value, None, result.agent, result.validation_status, tuple(warnings)
            )
        guarded = guard_interpretation(result.interpretation)
        if guarded.withheld:
            warnings.append(
                "The SLAI interpretation was withheld because "
                + " and ".join(guarded.reasons)
                + "."
            )
            return Explanation(
                "withheld", None, result.agent, result.validation_status, tuple(warnings)
            )
        review = await asyncio.to_thread(self._safety.review, guarded.text or "", purpose=purpose)
        if review.available and not review.allowed:
            warnings.append(
                "The SLAI interpretation was withheld by the safety review: "
                + "; ".join(review.blockers)
            )
            return Explanation(
                "withheld", None, result.agent, result.validation_status, tuple(warnings), review
            )
        warnings.extend(review.warnings)
        return Explanation(
            result.status.value,
            guarded.text,
            result.agent,
            result.validation_status,
            tuple(warnings),
            review,
        )
