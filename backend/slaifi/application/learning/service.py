"""Self-measurement and adaptation use cases.

* Check logged recommendations against what the real price later did (budget-aware).
* Suggest strategy tightening from how a paper portfolio actually behaved.
* Ask SLAI to review goals and suggestions; the deterministic figures stay authoritative.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from slaifi.application.contracts import FinanceStore, ReasoningRequest
from slaifi.application.goals import GoalTracker
from slaifi.application.learning.log import RecommendationLog
from slaifi.application.market import MarketDataService
from slaifi.application.paper import PaperTradingService
from slaifi.application.recommendations import Explanation, RecommendationService
from slaifi.application.strategies import StrategyService
from slaifi.core.utils.errors import SlaifiError
from slaifi.domain.assets import AssetClass
from slaifi.domain.goals import GoalFeasibilityReport
from slaifi.domain.learning import EVALUATION_TRADING_DAYS, RecommendationRecord, TrackRecord
from slaifi.domain.strategies import StrategyProfile
from slaifi.engines.learning import (
    AdaptationInputs,
    AdaptationReport,
    GoalSignal,
    propose_adaptations,
    score_outcome,
)
from slaifi.engines.portfolio import EquityPoint, summarize_performance

# 20 trading days is four calendar weeks, which is how far forward each call is judged.
EVALUATION_CALENDAR_DAYS = math.ceil(EVALUATION_TRADING_DAYS * 7 / 5)
MAX_SYMBOLS_PER_REFRESH = 8  # each symbol is one real data request; free tiers are small


@dataclass(frozen=True, slots=True)
class RefreshResult:
    evaluated: int
    waiting: int  # logged but not yet old enough
    unchecked_symbols: tuple[str, ...]  # old enough, but real prices were not obtainable
    deferred_symbols: int  # left for the next refresh to respect data-source limits
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class AdaptationView:
    strategy: StrategyProfile
    portfolio_id: str | None
    report: AdaptationReport
    track_record: TrackRecord
    explanation: Explanation | None


@dataclass(frozen=True, slots=True)
class GoalReview:
    report: GoalFeasibilityReport
    explanation: Explanation


class LearningService:
    def __init__(
        self,
        store: FinanceStore,
        log: RecommendationLog,
        market: MarketDataService,
        paper: PaperTradingService,
        strategies: StrategyService,
        goals: GoalTracker,
        recommender: RecommendationService,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._log = log
        self._market = market
        self._paper = paper
        self._strategies = strategies
        self._goals = goals
        self._recommender = recommender
        self._clock = clock or (lambda: datetime.now(UTC))

    # ------------------------------------------------------------------ track record
    def track_record(self) -> TrackRecord:
        return self._log.summary()

    async def refresh_outcomes(self) -> RefreshResult:
        now = self._clock()
        due = self._store.list_pending_recommendations(
            now - timedelta(days=EVALUATION_CALENDAR_DAYS)
        )
        all_pending = [
            record
            for record, outcome in self._store.list_recommendation_history()
            if outcome is None
        ]
        waiting = max(len(all_pending) - len(due), 0)
        by_symbol: dict[tuple[str, str, str | None], list[RecommendationRecord]] = {}
        for record in due:
            by_symbol.setdefault((record.symbol, record.asset_class, record.exchange), []).append(
                record
            )
        keys = list(by_symbol)
        chosen, deferred = keys[:MAX_SYMBOLS_PER_REFRESH], keys[MAX_SYMBOLS_PER_REFRESH:]
        evaluated = 0
        unchecked: list[str] = []
        for symbol, asset_class, exchange in chosen:
            try:
                asset = await self._market.resolve_asset(
                    symbol, exchange=exchange, asset_class=AssetClass(asset_class)
                )
                history = await self._market.history(asset, days=180, interval="1day")
            except SlaifiError:
                unchecked.append(symbol)
                continue
            if history.provenance.last_known or not history.bars:
                unchecked.append(symbol)  # stale prices must never settle a recommendation
                continue
            for record in by_symbol[(symbol, asset_class, exchange)]:
                target = record.issued_at + timedelta(days=EVALUATION_CALENDAR_DAYS)
                bar = next((b for b in history.bars if b.end_at >= target), None)
                if bar is None:
                    continue
                outcome = score_outcome(
                    record,
                    end_price=bar.close,
                    evaluated_at=now,
                    data_source=history.provenance.source or "",
                )
                self._store.save_recommendation_outcome(outcome)
                evaluated += 1
        notes: list[str] = []
        if deferred:
            notes.append(
                f"{len(deferred)} more symbol(s) are due; they will be checked on the next "
                "refresh so free data-source limits are respected."
            )
        return RefreshResult(evaluated, waiting, tuple(unchecked), len(deferred), tuple(notes))

    # ------------------------------------------------------------------ adaptation
    async def adaptations(
        self,
        strategy_id: str | None = None,
        *,
        portfolio_id: str | None = None,
        explain: bool = False,
    ) -> AdaptationView:
        strategy = self._strategies.resolve(strategy_id)
        record = self._log.summary()
        points: list[EquityPoint] = []
        largest: float | None = None
        cash_weight: float | None = None
        max_drawdown: float | None = None
        if portfolio_id is not None:
            view = await self._paper.view(portfolio_id, record=False)
            points = [
                EquityPoint(p.at, p.total_value, p.net_flow)
                for p in self._store.list_valuations(portfolio_id)
            ]
            max_drawdown = summarize_performance(points).max_drawdown
            weights = [
                p.portfolio_weight
                for p in view.snapshot.positions
                if p.portfolio_weight is not None
            ]
            largest = max(weights) if weights else None
            total = view.snapshot.total_value
            cash_weight = float(view.snapshot.cash_balance / total) if total > 0 else None
        report = propose_adaptations(
            AdaptationInputs(
                strategy=strategy,
                valuation_points=len(points),
                max_drawdown=max_drawdown,
                largest_position_weight=largest,
                cash_weight=cash_weight,
                track_record=record,
                goals=await self._goal_signals(portfolio_id),
            )
        )
        explanation = await self._explain_adaptations(strategy, report, record) if explain else None
        return AdaptationView(strategy, portfolio_id, report, record, explanation)

    async def _goal_signals(self, portfolio_id: str | None) -> list[GoalSignal]:
        signals: list[GoalSignal] = []
        for spec in self._goals.list():
            try:
                analysis = await self._goals.analyze_spec(
                    spec, portfolio_id=portfolio_id or spec.portfolio_id
                )
            except SlaifiError:
                continue
            behind = analysis.progress.on_track is False if analysis.progress else None
            signals.append(
                GoalSignal(
                    name=spec.name,
                    basis=spec.basis.value,
                    required_annual_return_rate=analysis.required_annual_return_rate,
                    behind_pace=behind,
                )
            )
        return signals

    async def _explain_adaptations(
        self, strategy: StrategyProfile, report: AdaptationReport, record: TrackRecord
    ) -> Explanation:
        request = ReasoningRequest(
            operation="strategy_adaptation_review",
            evidence={
                "strategy": {
                    "name": strategy.name,
                    "risk_tolerance": strategy.risk_tolerance.value,
                    "horizon_days": strategy.horizon_days,
                    "max_drawdown_rate": strategy.max_drawdown_rate,
                    "max_position_weight": strategy.max_position_weight,
                    "cash_reserve_rate": strategy.cash_reserve_rate,
                },
                "suggestions": [
                    {
                        "code": p.code,
                        "kind": p.kind,
                        "title": p.title,
                        "rationale": p.rationale,
                        "evidence": list(p.evidence),
                        "change": p.change,
                    }
                    for p in report.proposals
                ],
                "track_record": {
                    "decisive_results": record.scored,
                    "hit_rate": record.hit_rate,
                    "verdict": record.verdict.value,
                },
            },
            objective=(
                "In plain language, say how the suggested strategy adjustments relate to the "
                "measured evidence, which matter most, and what the person should check before "
                "applying any of them. Do not add new suggestions, numbers, predictions or "
                "personal advice, and do not recommend taking more risk."
            ),
            constraints={"suggestions_are_authoritative": True, "never_suggest_more_risk": True},
            assumptions={"rules_not_a_learned_model": True},
            uncertainty={"sample_size_for_track_record": record.scored},
        )
        return await self._recommender.run_reasoner(request, purpose="strategy_adaptation_review")

    # ------------------------------------------------------------------ goal review
    async def review_goal(
        self,
        goal_id: str,
        *,
        assumed_annual_return_rate: float | None = None,
        portfolio_id: str | None = None,
    ) -> GoalReview:
        report = await self._goals.analyze(
            goal_id,
            assumed_annual_return_rate=assumed_annual_return_rate,
            portfolio_id=portfolio_id,
        )
        spec = self._goals.get(goal_id)
        plan = report.plan
        evidence: dict[str, Any] = {
            "goal": {
                "name": spec.name,
                "basis": spec.basis.value,
                "currency": str(spec.currency),
                "horizon_years": spec.horizon_years,
            },
            "status": report.status.value,
            "capital_used": str(report.capital_used),
            "required_annual_return_rate": report.required_annual_return_rate,
            "assumed_annual_return_rate": report.assumed_annual_return_rate,
            "findings": [
                {"code": f.code, "severity": f.severity, "message": f.message}
                for f in report.findings
            ],
            "progress": report.progress.detail if report.progress else None,
            "plan": (
                {
                    "kind": plan.kind,
                    "note": plan.basis_note,
                    "required_monthly_contribution": str(plan.required_monthly_contribution)
                    if plan.required_monthly_contribution is not None
                    else None,
                    "balance_gap": str(plan.balance_gap) if plan.balance_gap is not None else None,
                    "months_capital_lasts": plan.months_capital_lasts,
                    "replanned_from_today": plan.replanned_from_today,
                }
                if plan
                else None
            ),
        }
        request = ReasoningRequest(
            operation="goal_plan_review",
            evidence=evidence,
            objective=(
                "Explain in plain language what this goal's arithmetic means for the person: "
                "what it requires, which findings matter most, and what trade-offs they have "
                "(target, time, saving, risk). Do not change any number, add return forecasts, "
                "or give personal advice."
            ),
            constraints={"figures_are_authoritative": True, "targets_are_not_guarantees": True},
            assumptions={"assumed_annual_return_rate": report.assumed_annual_return_rate},
            uncertainty={
                "return_assumption_supplied": report.assumed_annual_return_rate is not None
            },
        )
        explanation = await self._recommender.run_reasoner(request, purpose="goal_plan_review")
        return GoalReview(report, explanation)
