"""Persisted measurable goals: create, evaluate against a portfolio, measure progress."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from slaifi.application.contracts import FinanceStore
from slaifi.application.paper import PaperTradingService
from slaifi.application.strategies import StrategyService
from slaifi.core.types import CurrencyCode
from slaifi.core.utils.errors import NotFoundError, ValidationError
from slaifi.domain.goals import (
    GoalBasis,
    GoalFeasibilityReport,
    GoalProgress,
    GoalSpec,
    IncomePeriod,
)
from slaifi.domain.portfolio import CashFlowKind, Portfolio
from slaifi.engines.goals.planning import analyze_goal, annualize_measured_return, measure_progress
from slaifi.engines.portfolio import EquityPoint, build_positions, summarize_performance

_ZERO = Decimal("0")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def period_window(period: IncomePeriod, now: datetime) -> tuple[datetime, datetime, str]:
    """UTC calendar window containing ``now`` and its label."""

    day = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    if period is IncomePeriod.DAILY:
        return day, day + timedelta(days=1), f"today ({day:%Y-%m-%d} UTC)"
    if period is IncomePeriod.WEEKLY:
        start = day - timedelta(days=day.weekday())
        return start, start + timedelta(days=7), f"this week (from {start:%Y-%m-%d})"
    if period is IncomePeriod.MONTHLY:
        start = day.replace(day=1)
        end = (start + timedelta(days=32)).replace(day=1)
        return start, end, f"this month ({start:%B %Y})"
    if period is IncomePeriod.QUARTERLY:
        quarter_month = ((day.month - 1) // 3) * 3 + 1
        start = day.replace(month=quarter_month, day=1)
        end_month = quarter_month + 3
        end = (
            start.replace(year=start.year + 1, month=1)
            if end_month > 12
            else start.replace(month=end_month)
        )
        return start, end, f"this quarter (from {start:%Y-%m-%d})"
    start = day.replace(month=1, day=1)
    return start, start.replace(year=start.year + 1), f"this year ({start.year})"


class GoalTracker:
    def __init__(
        self,
        store: FinanceStore,
        paper: PaperTradingService,
        strategies: StrategyService,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._store = store
        self._paper = paper
        self._strategies = strategies
        self._clock = clock

    # ------------------------------------------------------------------ CRUD
    def list(self) -> list[GoalSpec]:
        return list(self._store.list_goals())

    def get(self, goal_id: str) -> GoalSpec:
        goal = self._store.get_goal(goal_id)
        if goal is None:
            raise NotFoundError(f"goal {goal_id!r} does not exist")
        return goal

    def create(self, fields: dict[str, Any], *, actor: str = "user") -> GoalSpec:
        try:
            spec = GoalSpec(
                goal_id=f"G-{uuid.uuid4().hex[:10]}",
                name=" ".join(str(fields["name"]).split())[:80],
                currency=CurrencyCode(str(fields.get("currency") or "USD").upper()),
                created_at=self._clock(),
                basis=GoalBasis(fields.get("basis") or GoalBasis.TOTAL_RETURN.value),
                target_amount=Decimal(str(fields["target_amount"]))
                if fields.get("target_amount") not in (None, "")
                else None,
                period=IncomePeriod(fields["period"]) if fields.get("period") else None,
                target_annual_rate=float(fields["target_annual_rate"])
                if fields.get("target_annual_rate") is not None
                else None,
                horizon_years=float(fields["horizon_years"])
                if fields.get("horizon_years") is not None
                else None,
                starting_capital=Decimal(str(fields["starting_capital"]))
                if fields.get("starting_capital") not in (None, "")
                else None,
                monthly_contribution=Decimal(str(fields.get("monthly_contribution") or "0")),
                monthly_withdrawal=Decimal(str(fields.get("monthly_withdrawal") or "0")),
                risk_tolerance=fields.get("risk_tolerance"),
                max_acceptable_drawdown_rate=(
                    float(fields["max_acceptable_drawdown_rate"])
                    if fields.get("max_acceptable_drawdown_rate") is not None
                    else None
                ),
                portfolio_id=fields.get("portfolio_id"),
            )
        except KeyError as exc:
            raise ValidationError(f"missing goal field {exc.args[0]!r}") from exc
        except (ArithmeticError, ValueError) as exc:
            if isinstance(exc, ValidationError):
                raise
            raise ValidationError(f"invalid goal: {exc}") from exc
        if spec.portfolio_id is not None:
            self._paper.get_portfolio(spec.portfolio_id)
        with self._store.transaction():
            self._store.save_goal(spec)
            self._store.append_audit(
                at=self._clock(),
                actor=actor,
                action="goal.created",
                subject=spec.goal_id,
                detail={
                    "name": spec.name,
                    "basis": spec.basis.value,
                    "target_amount": str(spec.target_amount) if spec.target_amount else None,
                    "period": spec.period.value if spec.period else None,
                    "target_annual_rate": spec.target_annual_rate,
                },
            )
        return spec

    def delete(self, goal_id: str, *, actor: str = "user") -> None:
        self.get(goal_id)
        with self._store.transaction():
            self._store.delete_goal(goal_id)
            self._store.append_audit(
                at=self._clock(), actor=actor, action="goal.deleted", subject=goal_id, detail={}
            )

    # ------------------------------------------------------------------ evaluation
    def _realized_between(self, ledger: Portfolio, start: datetime, end: datetime) -> Decimal:
        before = sum(
            (
                p.realized_pnl
                for p in build_positions([t for t in ledger.trades if t.occurred_at < start])
            ),
            _ZERO,
        )
        upto = sum(
            (
                p.realized_pnl
                for p in build_positions([t for t in ledger.trades if t.occurred_at < end])
            ),
            _ZERO,
        )
        return upto - before

    def _income_between(self, ledger: Portfolio, start: datetime, end: datetime) -> Decimal:
        return sum(
            (
                f.amount
                for f in ledger.cash_flows
                if f.kind is CashFlowKind.DIVIDEND and start <= f.occurred_at < end
            ),
            _ZERO,
        )

    def _measured_progress(
        self, spec: GoalSpec, portfolio_id: str | None, now: datetime
    ) -> GoalProgress | None:
        if spec.period is None or spec.target_amount is None or portfolio_id is None:
            return None
        start, end, label = period_window(spec.period, now)
        total = (end - start).total_seconds()
        elapsed = min(max((now - start).total_seconds() / total, 0.0), 1.0)
        ledger = self._store.load_ledger(portfolio_id)
        if spec.basis is GoalBasis.REALIZED_PROFIT:
            amount = self._realized_between(ledger, start, end)
        elif spec.basis is GoalBasis.INVESTMENT_INCOME:
            amount = self._income_between(ledger, start, end)
        else:
            points = [p for p in self._store.list_valuations(portfolio_id) if p.at < end]
            baseline = [p for p in points if p.at <= start]
            within = [p for p in points if p.at > start]
            if not points:
                return None
            first = baseline[-1] if baseline else points[0]
            last = points[-1]
            flows = sum((p.net_flow for p in within), _ZERO)
            amount = last.total_value - first.total_value - flows
        return measure_progress(
            spec, measured_amount=amount, window_label=label, elapsed_fraction=elapsed
        )

    async def analyze(
        self,
        goal_id: str,
        *,
        assumed_annual_return_rate: float | None = None,
        portfolio_id: str | None = None,
    ) -> GoalFeasibilityReport:
        spec = self.get(goal_id)
        return await self.analyze_spec(
            spec,
            assumed_annual_return_rate=assumed_annual_return_rate,
            portfolio_id=portfolio_id or spec.portfolio_id,
        )

    async def analyze_spec(
        self,
        spec: GoalSpec,
        *,
        assumed_annual_return_rate: float | None = None,
        portfolio_id: str | None = None,
        capital_override: Decimal | None = None,
    ) -> GoalFeasibilityReport:
        now = self._clock()
        strategy = self._strategies.active()
        capital = capital_override if capital_override is not None else spec.starting_capital
        measured_rate: float | None = None
        drawdown: float | None = None
        progress: GoalProgress | None = None
        if portfolio_id is not None:
            view = await self._paper.view(portfolio_id, record=False)
            if capital is None:
                capital = view.snapshot.total_value
            points = [
                EquityPoint(p.at, p.total_value, p.net_flow)
                for p in self._store.list_valuations(portfolio_id)
            ]
            summary = summarize_performance(
                points + [EquityPoint(now, view.snapshot.total_value, _ZERO)]
            )
            measured_rate = summary.annualized_return
            drawdown = summary.max_drawdown
            progress = self._measured_progress(spec, portfolio_id, now)
        if capital is None:
            capital = strategy.capital if strategy.capital is not None else _ZERO
        return analyze_goal(
            spec,
            capital=capital,
            assumed_annual_return_rate=assumed_annual_return_rate,
            measured_annual_return_rate=measured_rate,
            portfolio_max_drawdown=drawdown,
            strategy_max_drawdown_rate=strategy.max_drawdown_rate,
            strategy_risk_tolerance=strategy.risk_tolerance.value,
            progress=progress,
        )


__all__ = ["GoalTracker", "period_window", "annualize_measured_return"]
