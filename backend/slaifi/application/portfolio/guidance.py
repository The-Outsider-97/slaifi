"""Portfolio guidance: deterministic, quantified, strategy- and goal-aware observations."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from slaifi.application.contracts import ReasoningRequest
from slaifi.application.goals import GoalTracker
from slaifi.application.market import MarketDataService
from slaifi.application.paper import PaperTradingService, PortfolioView
from slaifi.application.recommendations import Explanation, RecommendationService
from slaifi.application.strategies import StrategyService
from slaifi.core.utils.errors import SlaifiError
from slaifi.domain.assets import AssetId
from slaifi.domain.goals import GoalFeasibilityReport
from slaifi.domain.recommendations import RecommendationAction, ReportStatus
from slaifi.domain.strategies import StrategyProfile
from slaifi.engines.strategy import AlignmentReport, evaluate_alignment

HIGH_CORRELATION = 0.80
IDLE_CASH_WEIGHT = 0.50
MAX_RECOMMENDATION_LOOKUPS = 8
_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2, "ok": 3}


@dataclass(frozen=True, slots=True)
class GuidanceItem:
    severity: str  # critical | warning | info | ok
    category: str  # limit | cash | concentration | diversification | goal | conditions | data
    title: str
    detail: str
    suggestion: str | None = None
    symbol: str | None = None
    quantity: str | None = None
    amount: str | None = None


@dataclass(frozen=True, slots=True)
class GoalGuidance:
    goal_id: str
    name: str
    status: str
    consistent: bool
    required_annual_return_rate: float | None
    measured_progress: str | None
    findings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HoldingSignal:
    symbol: str
    action: str | None
    status: str
    signal_score: float | None
    summary: str
    invalidation: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PortfolioGuidance:
    portfolio_id: str
    strategy: StrategyProfile
    aligned: bool
    items: tuple[GuidanceItem, ...]
    goals: tuple[GoalGuidance, ...]
    holdings: tuple[HoldingSignal, ...]
    metrics: dict[str, float | None]
    generated_at: datetime
    data_notes: tuple[str, ...] = ()
    explanation: Explanation | None = None


def _item_from_alignment(report: AlignmentReport) -> list[GuidanceItem]:
    items: list[GuidanceItem] = []
    suggestions = {(s.kind, s.symbol): s for s in report.suggestions}
    for finding in report.findings:
        severity = "critical" if finding.severity == "hard" else "warning"
        category = {
            "max_position_weight": "concentration",
            "concentration_hhi": "concentration",
            "cash_reserve": "cash",
            "drawdown_limit_breached": "limit",
        }.get(finding.code, "limit")
        suggestion = None
        symbol = None
        quantity = amount = None
        for (kind, sym), s in suggestions.items():
            if (
                (
                    finding.code == "max_position_weight"
                    and kind == "reduce_overweight"
                    and sym
                    and sym in finding.message
                )
                or (finding.code == "cash_reserve" and kind == "raise_cash")
                or (finding.code == "concentration_hhi" and kind == "diversify")
                or (finding.code == "drawdown_limit_breached" and kind == "de_risk")
                or (
                    finding.code
                    in {"excluded_asset", "prohibited_asset_class", "asset_class_not_allowed"}
                    and kind == "exit_disallowed_asset"
                    and sym
                    and sym in finding.message
                )
            ):
                suggestion, symbol = s.message, s.symbol
                quantity = str(s.quantity) if s.quantity is not None else None
                amount = str(s.amount) if s.amount is not None else None
                break
        items.append(
            GuidanceItem(
                severity,
                category,
                finding.code.replace("_", " ").capitalize(),
                finding.message,
                suggestion,
                symbol,
                quantity,
                amount,
            )
        )
    return items


class PortfolioGuidanceService:
    def __init__(
        self,
        paper: PaperTradingService,
        strategies: StrategyService,
        goals: GoalTracker,
        recommender: RecommendationService,
        market: MarketDataService,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._paper = paper
        self._strategies = strategies
        self._goals = goals
        self._recommender = recommender
        self._market = market
        self._clock = clock or (lambda: datetime.now(UTC))

    async def alignment(self, view: PortfolioView, strategy: StrategyProfile) -> AlignmentReport:
        vols: dict[AssetId, float] = {}

        async def one(asset: AssetId) -> None:
            try:
                stats = await self._market.stats(asset, days=400)
            except SlaifiError:
                return
            if stats.annualized_volatility is not None:
                vols[asset] = stats.annualized_volatility

        await asyncio.gather(*(one(p.valuation.position.asset) for p in view.positions))
        return evaluate_alignment(
            view.snapshot,
            strategy,
            portfolio_drawdown=self._paper.drawdown(view.portfolio.portfolio_id),
            annualized_volatility=vols,
        )

    async def guidance(
        self, portfolio_id: str, *, strategy_id: str | None = None, explain: bool = False
    ) -> PortfolioGuidance:
        view = await self._paper.view(portfolio_id, record=False)
        strategy = self._strategies.resolve(strategy_id or view.portfolio.strategy_id)
        alignment = await self.alignment(view, strategy)
        items = _item_from_alignment(alignment)
        notes = list(view.warnings)
        total = view.snapshot.total_value
        cash_weight = float(view.snapshot.cash_balance / total) if total > 0 else None

        if not view.positions:
            items.append(
                GuidanceItem(
                    "info",
                    "diversification",
                    "No holdings yet",
                    f"The portfolio is fully in cash ({view.snapshot.cash_balance:.2f} {view.snapshot.base_currency}).",
                    "Use Stock Analysis to review candidates against your strategy before placing a simulated order.",
                )
            )
        else:
            if len(view.positions) < 3:
                items.append(
                    GuidanceItem(
                        "info",
                        "diversification",
                        "Few holdings",
                        f"Only {len(view.positions)} position(s): results depend heavily on individual names.",
                        "Consider spreading across more assets or an index/ETF, within your strategy's limits.",
                    )
                )
            if (
                cash_weight is not None
                and cash_weight > IDLE_CASH_WEIGHT
                and strategy.risk_tolerance.value != "conservative"
            ):
                items.append(
                    GuidanceItem(
                        "info",
                        "cash",
                        "Large cash balance",
                        f"{cash_weight:.0%} of the portfolio is idle cash.",
                        "Review whether this matches your goal and horizon; cash earns nothing in this simulation.",
                    )
                )
            held = [p.valuation.position.asset for p in view.positions][:6]
            if len(held) >= 2:
                try:
                    compare = await self._market.compare(held, days=365)
                    seen: set[frozenset[str]] = set()
                    for a, row in compare.correlations.items():
                        for b, value in row.items():
                            key = frozenset((a, b))
                            if (
                                a != b
                                and key not in seen
                                and value is not None
                                and value >= HIGH_CORRELATION
                            ):
                                seen.add(key)
                                items.append(
                                    GuidanceItem(
                                        "warning",
                                        "diversification",
                                        "Holdings move together",
                                        f"{a} and {b} had a correlation of {value:.2f} over the last year, so they diversify little.",
                                        "Replace one with a less correlated asset if diversification matters for your goals.",
                                    )
                                )
                    notes.extend(compare.notes)
                except SlaifiError as exc:
                    notes.append(f"Correlation analysis unavailable: {exc.message}")

        goal_rows: list[GoalGuidance] = []
        for goal in self._goals.list():
            if goal.portfolio_id not in (None, portfolio_id):
                continue
            try:
                report: GoalFeasibilityReport = await self._goals.analyze(
                    goal.goal_id, portfolio_id=portfolio_id
                )
            except SlaifiError as exc:
                notes.append(f"Goal {goal.name!r} could not be evaluated: {exc.message}")
                continue
            goal_rows.append(self._goal_guidance(goal.name, report))
            worst = next((f for f in report.findings if f.severity == "critical"), None) or next(
                (f for f in report.findings if f.severity == "warning"), None
            )
            if worst is not None:
                items.append(
                    GuidanceItem(
                        "critical" if worst.severity == "critical" else "warning",
                        "goal",
                        f"Goal: {goal.name}",
                        worst.message,
                        "Review the goal's scenarios or adjust the target, horizon or capital.",
                    )
                )
            elif report.progress and report.progress.on_track is False:
                items.append(
                    GuidanceItem(
                        "warning", "goal", f"Goal behind pace: {goal.name}", report.progress.detail
                    )
                )

        holdings: list[HoldingSignal] = []
        for p in view.positions[:MAX_RECOMMENDATION_LOOKUPS]:
            symbol = p.valuation.position.asset.symbol
            try:
                rec = await self._recommender.recommend(
                    symbol,
                    strategy_id=strategy.strategy_id,
                    portfolio_id=portfolio_id,
                    exchange=p.valuation.position.asset.exchange,
                )
            except SlaifiError as exc:
                holdings.append(HoldingSignal(symbol, None, "unavailable", None, exc.message, ()))
                continue
            r = rec.report
            holdings.append(
                HoldingSignal(
                    symbol,
                    r.action.value if r.action else None,
                    r.status.value,
                    r.signal_score,
                    r.summary,
                    r.invalidation_conditions,
                )
            )
            if r.status is ReportStatus.RECOMMENDATION and r.action in {
                RecommendationAction.SELL,
                RecommendationAction.REDUCE,
            }:
                items.append(
                    GuidanceItem(
                        "warning",
                        "conditions",
                        f"Signals weakened: {symbol}",
                        f"The rules now say {r.action.value} (score {r.signal_score:+.2f}).",
                        "Review the position; see the stock analysis for the evidence and invalidation conditions.",
                        symbol=symbol,
                    )
                )
            elif r.status is ReportStatus.INSUFFICIENT_EVIDENCE:
                notes.append(
                    f"{symbol}: {r.insufficient_reasons[0] if r.insufficient_reasons else 'insufficient evidence'}"
                )

        if not any(i.severity in {"critical", "warning"} for i in items):
            items.append(
                GuidanceItem(
                    "ok",
                    "limit",
                    "Within your strategy",
                    "No hard limit is breached and no warning applies to the current holdings.",
                )
            )
        items.sort(key=lambda i: _SEVERITY_ORDER[i.severity])
        metrics: dict[str, float | None] = dict(alignment.metrics)
        metrics["position_count"] = float(len(view.positions))
        result = PortfolioGuidance(
            portfolio_id=portfolio_id,
            strategy=strategy,
            aligned=alignment.aligned,
            items=tuple(items),
            goals=tuple(goal_rows),
            holdings=tuple(holdings),
            metrics=metrics,
            generated_at=self._clock(),
            data_notes=tuple(dict.fromkeys(notes)),
        )
        if explain:
            explanation = await self._explain(result)
            return replace(result, explanation=explanation)
        return result

    @staticmethod
    def _goal_guidance(name: str, report: GoalFeasibilityReport) -> GoalGuidance:
        return GoalGuidance(
            goal_id=report.goal_id,
            name=name,
            status=report.status.value,
            consistent=report.consistent,
            required_annual_return_rate=report.required_annual_return_rate,
            measured_progress=report.progress.detail if report.progress else None,
            findings=tuple(f.message for f in report.findings if f.severity != "info"),
        )

    async def _explain(self, guidance: PortfolioGuidance) -> Explanation:
        evidence: dict[str, Any] = {
            "strategy": {
                "name": guidance.strategy.name,
                "risk_tolerance": guidance.strategy.risk_tolerance.value,
                "horizon_days": guidance.strategy.horizon_days,
            },
            "aligned_with_hard_limits": guidance.aligned,
            "items": [
                {
                    "severity": i.severity,
                    "category": i.category,
                    "title": i.title,
                    "detail": i.detail,
                    "suggestion": i.suggestion,
                }
                for i in guidance.items
            ],
            "goals": [
                {
                    "name": g.name,
                    "status": g.status,
                    "required_annual_return_rate": g.required_annual_return_rate,
                    "findings": list(g.findings),
                }
                for g in guidance.goals
            ],
            "holdings": [
                {
                    "symbol": h.symbol,
                    "action": h.action,
                    "status": h.status,
                    "score": h.signal_score,
                }
                for h in guidance.holdings
            ],
            "metrics": guidance.metrics,
        }
        request = ReasoningRequest(
            operation="portfolio_guidance_explanation",
            evidence=evidence,
            objective=(
                "Summarise, in plain language, how the current paper portfolio sits against the user's strategy "
                "and goals, which observations matter most and why, and what trade-offs exist. Use only the "
                "supplied evidence; do not invent figures, probabilities or new recommendations."
            ),
            constraints={"hard_limits_override_preferences": True},
        )
        return await self._recommender.run_reasoner(request, purpose="portfolio_guidance")
