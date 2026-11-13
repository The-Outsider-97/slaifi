"""Explicit JSON shapes returned by the SLAIFI API.

Money and quantities are strings (exact decimals); rates are floats (``0.05`` = 5%). Every
response that carries market data includes ``provenance`` so a client can always show whether it
is looking at live, delayed, last-known or unavailable data and how old an observation is.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from slaifi.application.advisor import AdvisorResult, ConfirmResult
from slaifi.application.contracts import (
    AgentStatus,
    KnowledgeAnswer,
    LearningRecall,
    LearningShare,
    ReconciliationReport,
    SafetyReview,
)
from slaifi.application.learning import AdaptationView, GoalReview, RefreshResult
from slaifi.application.market import (
    ComparisonView,
    DataProvenance,
    HistoryStats,
    HistoryView,
    QuoteView,
    SearchView,
)
from slaifi.application.paper import HistoryEntry, OrderOutcome, PerformanceView, PortfolioView
from slaifi.application.portfolio import PortfolioGuidance
from slaifi.application.recommendations import (
    BacktestResult,
    BacktestView,
    Explanation,
    RecommendationView,
)
from slaifi.domain.assets import AssetId
from slaifi.domain.goals import GoalFeasibilityReport, GoalSpec
from slaifi.domain.learning import TrackRecord
from slaifi.domain.ledger import AuditEntry, Proposal, WatchlistItem
from slaifi.domain.market import (
    InstrumentInfo,
    OHLCVBar,
    ProviderCheck,
    ProviderKeyInfo,
    ProviderStatus,
)
from slaifi.domain.paper import OrderDecision, PaperPortfolio, PlatformFees
from slaifi.domain.recommendations import RecommendationReport
from slaifi.domain.strategies import PRESET_DESCRIPTIONS, StrategyProfile


def d(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def t(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def asset(a: AssetId) -> dict[str, Any]:
    return {
        "symbol": a.symbol,
        "display_symbol": a.display_symbol,
        "asset_class": a.asset_class.value,
        "exchange": a.exchange,
        "currency": str(a.currency) if a.currency is not None else None,
    }


def provenance(p: DataProvenance) -> dict[str, Any]:
    return {
        "mode": p.mode,
        "available": p.available,
        "source": p.source,
        "last_known": p.last_known,
        "saved_at": t(p.saved_at),
        "delayed": p.delayed,
        "market_open": p.market_open,
        "observed_at": t(p.observed_at),
        "retrieved_at": t(p.retrieved_at),
        "age_seconds": p.age_seconds,
        "attempts": [
            {"source": a.source, "outcome": a.outcome, "detail": a.detail} for a in p.attempts
        ],
        "notes": list(p.notes),
    }


def instrument(i: InstrumentInfo) -> dict[str, Any]:
    return {
        "asset": asset(i.asset),
        "name": i.name,
        "country": i.country,
        "instrument_type": i.instrument_type,
    }


def search(view: SearchView) -> dict[str, Any]:
    return {
        "query": view.query,
        "supported": view.supported,
        "results": [instrument(i) for i in view.results],
        "provenance": provenance(view.provenance),
    }


def quote(view: QuoteView) -> dict[str, Any]:
    q = view.quote
    if q is None:  # nothing live and nothing saved: the UI shows NOT AVAILABLE
        return {
            "asset": asset(view.asset),
            "available": False,
            "price": None,
            "currency": None,
            "change_rate": None,
            "previous_close": None,
            "observed_at": None,
            "source": None,
            "last_known": False,
            "provenance": provenance(view.provenance),
        }
    return {
        "asset": asset(q.asset),
        "available": True,
        "price": d(q.price),
        "currency": str(q.currency),
        "change_rate": q.change_rate,
        "previous_close": d(q.previous_close),
        "observed_at": t(q.observed_at),
        "source": q.source,
        "last_known": q.last_known,
        "provenance": provenance(view.provenance),
    }


def provider_status(s: ProviderStatus) -> dict[str, Any]:
    return {
        "name": s.name,
        "label": s.label,
        "configured": s.configured,
        "capabilities": list(s.capabilities),
        "intervals": list(s.intervals),
        "state": s.state,
        "cooldown_until": t(s.cooldown_until),
        "last_success_at": t(s.last_success_at),
        "last_error": s.last_error,
        "last_error_at": t(s.last_error_at),
        "calls_last_minute": s.calls_last_minute,
        "calls_today": s.calls_today,
        "free_tier_note": s.free_tier_note,
    }


def platform_fees(fees: PlatformFees) -> dict[str, Any]:
    return {"per_trade": d(fees.per_trade), "per_withdrawal": d(fees.per_withdrawal)}


def provider_key(k: ProviderKeyInfo) -> dict[str, Any]:
    """Where a source's key comes from. The key itself is never part of any answer."""

    return {
        "name": k.name,
        "label": k.label,
        "env_var": k.env_var,
        "configured": k.source is not None,
        "source": k.source,
    }


def provider_check(c: ProviderCheck) -> dict[str, Any]:
    return {
        "name": c.name,
        "configured": c.configured,
        "ok": c.ok,
        "detail": c.detail,
        "latency_ms": c.latency_ms,
    }


def bar(b: OHLCVBar) -> dict[str, Any]:
    return {
        "start_at": t(b.start_at),
        "end_at": t(b.end_at),
        "open": d(b.open),
        "high": d(b.high),
        "low": d(b.low),
        "close": d(b.close),
        "volume": d(b.volume),
    }


def series(view: HistoryView) -> dict[str, Any]:
    q = view.quality
    return {
        "asset": asset(view.asset),
        "interval": view.interval,
        "requested_days": view.requested_days,
        "bars": [bar(b) for b in view.bars],
        "overlays": {k: list(v) for k, v in view.overlays.items()},
        "quality": {
            "count": q.count,
            "first_at": t(q.first_at),
            "last_at": t(q.last_at),
            "duplicates_removed": q.duplicates_removed,
            "reordered": q.reordered,
            "gap_count": q.gap_count,
            "largest_gap_days": q.largest_gap_days,
            "complete": q.complete,
        },
        "notes": list(view.notes),
        "provenance": provenance(view.provenance),
    }


def stats(s: HistoryStats) -> dict[str, Any]:
    return {
        "asset": asset(s.asset),
        "interval": s.interval,
        "observation_count": s.observation_count,
        "start_at": t(s.start_at),
        "end_at": t(s.end_at),
        "first_close": s.first_close,
        "last_close": s.last_close,
        "period_return": s.period_return,
        "annualized_volatility": s.annualized_volatility,
        "periods_per_year": s.periods_per_year,
        "max_drawdown": s.max_drawdown,
        "current_drawdown": s.current_drawdown,
        "period_high": s.period_high,
        "period_low": s.period_low,
        "average_volume": s.average_volume,
        "best_period_return": s.best_period_return,
        "worst_period_return": s.worst_period_return,
        "sma_20": s.sma_20,
        "sma_50": s.sma_50,
        "rsi_14": s.rsi_14,
        "notes": list(s.notes),
        "provenance": provenance(s.provenance),
    }


def comparison(c: ComparisonView) -> dict[str, Any]:
    return {
        "interval": c.interval,
        "timestamps": [t(x) for x in c.timestamps],
        "series": [
            {
                "asset": asset(s.asset),
                "indexed": list(s.indexed),
                "period_return": s.period_return,
                "annualized_volatility": s.annualized_volatility,
                "max_drawdown": s.max_drawdown,
            }
            for s in c.series
        ],
        "correlations": c.correlations,
        "notes": list(c.notes),
        "provenance": provenance(c.provenance),
    }


def watchlist_item(item: WatchlistItem, view: QuoteView | None) -> dict[str, Any]:
    return {
        "asset": asset(item.asset),
        "name": item.name,
        "added_at": t(item.added_at),
        "quote": quote(view) if view else None,
    }


def safety(s: SafetyReview | None) -> dict[str, Any] | None:
    if s is None:
        return None
    return {
        "available": s.available,
        "allowed": s.allowed,
        "risk_level": s.risk_level,
        "blockers": list(s.blockers),
        "warnings": list(s.warnings),
        "reviewer": s.reviewer,
        "detail": s.detail,
    }


def explanation(e: Explanation | None) -> dict[str, Any] | None:
    if e is None:
        return None
    return {
        "status": e.status,
        "text": e.text,
        "agent": e.agent,
        "validation_status": e.validation_status,
        "warnings": list(e.warnings),
        "safety": safety(e.safety),
        "label": "SLAI interpretation. It explains the deterministic result and never changes it.",
    }


def report(r: RecommendationReport) -> dict[str, Any]:
    pred = r.prediction
    pv = r.prediction_validation
    return {
        "asset": asset(r.asset),
        "generated_at": t(r.generated_at),
        "horizon_days": r.horizon_days,
        "strategy_id": r.strategy_id,
        "status": r.status.value,
        "action": r.action.value if r.action else None,
        "signal_score": r.signal_score,
        "score_note": "Rule-based aggregate from −1 to +1. It is not a probability or a confidence level.",
        "risk_level": r.risk_level.value if r.risk_level else None,
        "signals": [
            {
                "name": s.name,
                "value": s.value,
                "direction": s.direction.value,
                "weight": s.weight,
                "vote": s.vote,
                "rationale": s.rationale,
            }
            for s in r.signals
        ],
        "supporting_signals": list(r.supporting_signals),
        "conflicting_signals": list(r.conflicting_signals),
        "invalidation_conditions": list(r.invalidation_conditions),
        "constraint_findings": [
            {
                "code": f.code,
                "severity": f.severity,
                "message": f.message,
                "limit": f.limit,
                "observed": f.observed,
            }
            for f in r.constraint_findings
        ],
        "insufficient_reasons": list(r.insufficient_reasons),
        "prediction": (
            {
                "horizon_days": pred.horizon.days,
                "model": {"name": pred.model_name, "version": pred.model_version},
                "interval": (
                    {
                        "lower_return_rate": pred.interval.lower_return_rate,
                        "upper_return_rate": pred.interval.upper_return_rate,
                        "nominal_coverage": pred.interval.coverage_probability,
                    }
                    if pred.interval
                    else None
                ),
                "median_historical_return_rate": pred.expected_return_rate,
                "input_data_at": t(pred.input_data_at),
            }
            if pred
            else None
        ),
        "prediction_validation": (
            {
                "method": pv.method,
                "nominal_coverage": pv.nominal_coverage,
                "realized_coverage": pv.realized_coverage,
                "test_count": pv.test_count,
                "mean_interval_width": pv.mean_interval_width,
                "passed": pv.passed,
                "note": pv.note,
            }
            if pv
            else None
        ),
        "expected_downside_rate": r.expected_downside_rate,
        "observation_count": r.observation_count,
        "last_bar_at": t(r.last_bar_at),
        "data_mode": r.data_mode,
        "last_known": r.last_known,
        "position_quantity": r.position_quantity,
        "model_versions": [{"name": m.name, "version": m.version} for m in r.model_versions],
        "summary": r.summary,
        "notes": list(r.notes),
    }


def recommendation(v: RecommendationView) -> dict[str, Any]:
    return {
        "report": report(v.report),
        "strategy": {"strategy_id": v.strategy.strategy_id, "name": v.strategy.name},
        "provenance": provenance(v.provenance),
        "explanation": explanation(v.explanation),
        "history_notes": list(v.history_notes),
        "disclaimer": "Decision support only. Not investment advice.",
    }


def backtest_result(r: BacktestResult) -> dict[str, Any]:
    return {
        "strategy_id": r.strategy_id,
        "bar_count": r.bar_count,
        "start_at": t(r.start_at),
        "end_at": t(r.end_at),
        "total_return": r.total_return,
        "annualized_return": r.annualized_return,
        "max_drawdown": r.max_drawdown,
        "exposure_rate": r.exposure_rate,
        "trade_count": r.trade_count,
        "win_rate": r.win_rate,
        "benchmark": {
            "label": "Buy and hold, same costs",
            "total_return": r.benchmark_total_return,
            "annualized_return": r.benchmark_annualized_return,
            "max_drawdown": r.benchmark_max_drawdown,
        },
        "excess_return": r.excess_return,
        "first_half_return": r.first_half_return,
        "second_half_return": r.second_half_return,
        "costs": {"commission_rate": r.commission_rate, "slippage_rate": r.slippage_rate},
        "trades": [
            {
                "entered_at": t(x.entered_at),
                "exited_at": t(x.exited_at),
                "entry_price": x.entry_price,
                "exit_price": x.exit_price,
                "return_rate": x.return_rate,
            }
            for x in r.trades
        ],
        "assumptions": list(r.assumptions),
    }


def backtest(v: BacktestView) -> dict[str, Any]:
    return {
        "symbol": v.symbol,
        "strategy": {"strategy_id": v.strategy.strategy_id, "name": v.strategy.name},
        "result": backtest_result(v.result) if v.result else None,
        "message": v.message,
        "provenance": provenance(v.provenance),
        "disclaimer": "A historical simulation, not a forecast and not investment advice.",
    }


def strategy(s: StrategyProfile) -> dict[str, Any]:
    c = s.constraints
    return {
        "strategy_id": s.strategy_id,
        "name": s.name,
        "preset": s.preset,
        "preset_description": PRESET_DESCRIPTIONS.get(s.preset or ""),
        "risk_tolerance": s.risk_tolerance.value,
        "horizon_days": s.horizon_days,
        "horizon_bucket": s.horizon.value,
        "capital": d(s.capital),
        "max_position_weight": c.max_position_weight,
        "max_drawdown_rate": c.max_drawdown_rate,
        "max_short_exposure": c.max_short_exposure or 0.0,
        "cash_reserve_rate": s.cash_reserve_rate,
        "max_annualized_volatility": s.max_annualized_volatility,
        "max_concentration_hhi": s.max_concentration_hhi,
        "excluded_symbols": sorted(s.excluded_symbols),
        "prohibited_asset_classes": sorted(a.value for a in c.prohibited_asset_classes),
        "allowed_asset_classes": sorted(a.value for a in c.allowed_asset_classes),
        "preferred_asset_classes": sorted(a.value for a in s.preferred_asset_classes),
        "trading_frequency": s.trading_frequency.value,
        "income_weight": s.income_weight,
        "commission_rate": d(s.costs.commission_rate),
        "commission_minimum": d(s.costs.commission_minimum),
        "slippage_rate": d(s.costs.slippage_rate),
        "reinvest_dividends": s.reinvest_dividends,
    }


def portfolio_meta(p: PaperPortfolio) -> dict[str, Any]:
    return {
        "portfolio_id": p.portfolio_id,
        "name": p.name,
        "base_currency": str(p.base_currency),
        "starting_capital": d(p.starting_capital),
        "strategy_id": p.strategy_id,
        "created_at": t(p.created_at),
        "epoch": p.epoch,
    }


def portfolio_view(v: PortfolioView) -> dict[str, Any]:
    s = v.snapshot
    total = s.total_value
    positions = []
    for p in v.positions:
        val = p.valuation
        pos = val.position
        positions.append(
            {
                "asset": asset(pos.asset),
                "quantity": d(pos.quantity),
                "direction": "short" if pos.quantity < 0 else "long",
                "average_cost": d(pos.average_cost),
                "market_price": d(val.market_price),
                "market_value": d(val.market_value),
                "unrealized_pnl": d(val.unrealized_pnl),
                "realized_pnl": d(pos.realized_pnl),
                "weight": val.portfolio_weight,
                "price_basis": p.price_basis,
                "stale_price": p.stale,
                "price_provenance": provenance(p.quote.provenance) if p.quote else None,
            }
        )
    return {
        "portfolio": portfolio_meta(v.portfolio),
        "as_of": t(v.as_of),
        "currency": str(s.base_currency),
        "cash_balance": d(s.cash_balance),
        "invested_value": d(s.securities_market_value),
        "short_value": d(s.short_value),
        "margin_required": d(s.margin_required),
        "free_cash": d(s.free_cash),
        "short_exposure": float(s.short_value / total) if total > 0 else None,
        "total_value": d(total),
        "cash_weight": float(s.cash_balance / total) if total > 0 else None,
        "net_contributions": d(v.net_contributions),
        "total_pnl": d(v.total_pnl),
        "simple_return": v.simple_return,
        "realized_pnl": d(v.realized_pnl),
        "unrealized_pnl": d(v.unrealized_pnl),
        "fees_paid": d(v.fees_paid),
        "slippage_cost": d(v.slippage_cost),
        "positions": positions,
        "valuation_complete": v.valuation_complete,
        "simulated": True,
        "warnings": list(v.warnings),
    }


def decision(dec: OrderDecision) -> dict[str, Any]:
    ex = dec.execution
    tr = dec.trade
    return {
        "status": dec.status.value,
        "rejections": [{"code": r.code.value, "message": r.message} for r in dec.rejections],
        "warnings": list(dec.warnings),
        "trade": (
            {
                "trade_id": tr.trade_id,
                "side": tr.side.value,
                "quantity": d(tr.quantity),
                "unit_price": d(tr.unit_price),
                "fee": d(tr.fee),
                "occurred_at": t(tr.occurred_at),
            }
            if tr
            else None
        ),
        "execution": (
            {
                "quote_price": d(ex.quote_price),
                "execution_price": d(ex.execution_price),
                "slippage_per_unit": d(ex.slippage_per_unit),
                "commission": d(ex.commission),
                "gross_amount": d(ex.gross_amount),
                "net_cash_effect": d(ex.net_cash_effect),
                "currency": str(ex.currency),
                "quote_observed_at": t(ex.quote_observed_at),
                "quote_source": ex.quote_source,
                "data_mode": ex.data_mode,
                "executed_at": t(ex.executed_at),
                "market_open": ex.market_open,
                "notes": list(ex.notes),
            }
            if ex
            else None
        ),
        "simulated": True,
    }


def order_outcome(o: OrderOutcome) -> dict[str, Any]:
    return {
        "decision": decision(o.decision),
        "asset": asset(o.asset),
        "duplicate": o.duplicate,
        "dry_run": o.dry_run,
        "strategy_id": o.strategy_id,
        "portfolio": portfolio_view(o.portfolio) if o.portfolio else None,
    }


def history_entry(h: HistoryEntry) -> dict[str, Any]:
    return {"at": t(h.at), "kind": h.kind, "summary": h.summary, "detail": h.detail}


def performance(p: PerformanceView) -> dict[str, Any]:
    s = p.summary
    return {
        "portfolio_id": p.portfolio_id,
        "point_count": s.point_count,
        "start_at": t(s.start_at),
        "end_at": t(s.end_at),
        "time_weighted_return": s.time_weighted_return,
        "annualized_return": s.annualized_return,
        "max_drawdown": s.max_drawdown,
        "current_drawdown": s.current_drawdown,
        "net_profit": d(s.net_profit),
        "net_contributions": d(p.net_contributions),
        "total_pnl": d(p.total_pnl),
        "simple_return": p.simple_return,
        "realized_pnl": d(p.realized_pnl),
        "unrealized_pnl": d(p.unrealized_pnl),
        "fees_paid": d(p.fees_paid),
        "slippage_cost": d(p.slippage_cost),
        "exposure": p.exposure,
        "cash_weight": p.cash_weight,
        "largest_position_weight": p.largest_position_weight,
        "concentration_hhi": p.concentration_hhi,
        "equity_curve": [{"at": t(at), "value": d(v)} for at, v in p.equity_curve],
        "notes": list(p.notes),
    }


def goal(g: GoalSpec) -> dict[str, Any]:
    return {
        "goal_id": g.goal_id,
        "name": g.name,
        "currency": str(g.currency),
        "created_at": t(g.created_at),
        "basis": g.basis.value,
        "target_amount": d(g.target_amount),
        "period": g.period.value if g.period else None,
        "target_annual_rate": g.target_annual_rate,
        "horizon_years": g.horizon_years,
        "starting_capital": d(g.starting_capital),
        "monthly_contribution": d(g.monthly_contribution),
        "monthly_withdrawal": d(g.monthly_withdrawal),
        "risk_tolerance": g.risk_tolerance,
        "max_acceptable_drawdown_rate": g.max_acceptable_drawdown_rate,
        "portfolio_id": g.portfolio_id,
        "target_value": d(g.target_value),
    }


def goal_report(r: GoalFeasibilityReport) -> dict[str, Any]:
    prog = r.progress
    return {
        "goal_id": r.goal_id,
        "consistent": r.consistent,
        "status": r.status.value,
        "capital_used": d(r.capital_used),
        "annual_target_amount": d(r.annual_target_amount),
        "required_annual_return_rate": r.required_annual_return_rate,
        "required_capital_at_assumed_rate": d(r.required_capital_at_assumed_rate),
        "assumed_annual_return_rate": r.assumed_annual_return_rate,
        "scenarios": [
            {
                "label": s.label,
                "annual_return_rate": s.annual_return_rate,
                "source": s.source,
                "projected_value": d(s.projected_value),
                "period_profit": d(s.period_profit),
                "shortfall": d(s.shortfall),
                "meets_target": s.meets_target,
                "stress_loss": d(s.stress_loss),
            }
            for s in r.scenarios
        ],
        "findings": [
            {"code": f.code, "severity": f.severity, "message": f.message} for f in r.findings
        ],
        "assumptions": list(r.assumptions),
        "progress": (
            {
                "basis": prog.basis.value,
                "window": prog.window_label,
                "measured_amount": d(prog.measured_amount),
                "target_amount": d(prog.target_amount),
                "progress_ratio": prog.progress_ratio,
                "on_track": prog.on_track,
                "detail": prog.detail,
            }
            if prog
            else None
        ),
        "plan": (
            {
                "kind": r.plan.kind,
                "basis_note": r.plan.basis_note,
                "capital": d(r.plan.capital),
                "years_used": r.plan.years_used,
                "required_annual_return_rate": r.plan.required_annual_return_rate,
                "required_monthly_contribution": d(r.plan.required_monthly_contribution),
                "projected_balance": d(r.plan.projected_balance),
                "balance_gap": d(r.plan.balance_gap),
                "months_capital_lasts": r.plan.months_capital_lasts,
                "lasts_beyond_100_years": r.plan.lasts_beyond_100_years,
                "sustainable_monthly_withdrawal": d(r.plan.sustainable_monthly_withdrawal),
                "replanned_from_today": r.plan.replanned_from_today,
            }
            if r.plan
            else None
        ),
        "disclaimer": "Targets are objectives, not guarantees. Scenario rates are hypothetical or user-supplied.",
    }


def proposal(p: Proposal | None) -> dict[str, Any] | None:
    if p is None:
        return None
    return {
        "proposal_id": p.proposal_id,
        "created_at": t(p.created_at),
        "expires_at": t(p.expires_at),
        "status": p.status,
        "kind": p.kind,
    }


def advisor(r: AdvisorResult) -> dict[str, Any]:
    def change(c: Any) -> dict[str, Any]:
        return {
            "index": c.index,
            "field": c.field,
            "old": c.old,
            "new": c.new,
            "persistence": c.persistence,
            "description": c.description,
            "hard_limit": c.hard_limit,
            "loosens_limit": c.loosening,
        }

    return {
        "text": r.text,
        "blocked": r.blocked,
        "unrecognised": r.unrecognised,
        "intents": list(r.intents),
        "understood": list(r.understood),
        "safety": safety(r.safety),
        "changes": [change(c) for c in r.changes],
        "temporary_changes": [change(c) for c in r.temporary_changes],
        "temporary_analysis": (
            {
                "description": r.temporary_analysis.description,
                "changes": list(r.temporary_analysis.changes),
                "new_findings": list(r.temporary_analysis.new_findings),
                "resolved_findings": list(r.temporary_analysis.resolved_findings),
                "aligned_before": r.temporary_analysis.aligned_before,
                "aligned_after": r.temporary_analysis.aligned_after,
            }
            if r.temporary_analysis
            else None
        ),
        "goals": [
            {
                "name": g.draft.name,
                "draft": {
                    "target_amount": g.draft.target_amount,
                    "period": g.draft.period,
                    "target_annual_rate": g.draft.target_annual_rate,
                    "horizon_years": g.draft.horizon_years,
                    "basis": g.draft.basis,
                    "starting_capital": g.draft.starting_capital,
                },
                "report": goal_report(g.report) if g.report else None,
                "error": g.error,
            }
            for g in r.goals
        ],
        "orders": [
            {
                "draft": {
                    "side": o.draft.side,
                    "symbol": o.draft.symbol,
                    "quantity": o.draft.quantity,
                    "notional": o.draft.notional,
                    "close_position": o.draft.close_position,
                },
                "preview": order_outcome(o.outcome) if o.outcome else None,
                "error": o.error,
            }
            for o in r.orders
        ],
        "contradictions": [
            {"description": c.description, "fields": list(c.fields)} for c in r.contradictions
        ],
        "warnings": list(r.warnings),
        "explanation": explanation(r.explanation),
        "proposal": proposal(r.proposal),
        "requires_confirmation": r.requires_confirmation,
        "needs_acknowledgement_of_limits": r.needs_acknowledgement_of_limits,
        "needs_acknowledgement_of_contradictions": r.needs_acknowledgement_of_contradictions,
        "disclaimer": "Nothing changes until you confirm. Decision support only; not investment advice.",
    }


def confirm(r: ConfirmResult) -> dict[str, Any]:
    return {
        "proposal_id": r.proposal_id,
        "applied_changes": list(r.applied_changes),
        "created_goal_ids": list(r.created_goal_ids),
        "orders": [order_outcome(o) for o in r.orders],
        "strategy": strategy(r.strategy),
    }


def guidance(g: PortfolioGuidance) -> dict[str, Any]:
    return {
        "portfolio_id": g.portfolio_id,
        "strategy": {"strategy_id": g.strategy.strategy_id, "name": g.strategy.name},
        "aligned": g.aligned,
        "generated_at": t(g.generated_at),
        "items": [
            {
                "severity": i.severity,
                "category": i.category,
                "title": i.title,
                "detail": i.detail,
                "suggestion": i.suggestion,
                "symbol": i.symbol,
                "quantity": i.quantity,
                "amount": i.amount,
            }
            for i in g.items
        ],
        "goals": [
            {
                "goal_id": x.goal_id,
                "name": x.name,
                "status": x.status,
                "consistent": x.consistent,
                "required_annual_return_rate": x.required_annual_return_rate,
                "measured_progress": x.measured_progress,
                "findings": list(x.findings),
            }
            for x in g.goals
        ],
        "holdings": [
            {
                "symbol": h.symbol,
                "action": h.action,
                "status": h.status,
                "signal_score": h.signal_score,
                "summary": h.summary,
                "invalidation_conditions": list(h.invalidation),
            }
            for h in g.holdings
        ],
        "metrics": g.metrics,
        "data_notes": list(g.data_notes),
        "explanation": explanation(g.explanation),
        "disclaimer": "Decision support only. Not investment advice.",
    }


def reconciliation(r: ReconciliationReport) -> dict[str, Any]:
    return {
        "portfolio_id": r.portfolio_id,
        "checked_at": t(r.checked_at),
        "consistent": r.consistent,
        "trade_count": r.trade_count,
        "cash_flow_count": r.cash_flow_count,
        "cash_balance": d(r.cash_balance),
        "database_integrity": r.database_integrity,
        "audit_chain_intact": r.audit_chain_intact,
        "issues": [
            {"severity": i.severity, "code": i.code, "message": i.message} for i in r.issues
        ],
    }


def audit_entry(a: AuditEntry) -> dict[str, Any]:
    return {
        "seq": a.seq,
        "at": t(a.at),
        "actor": a.actor,
        "action": a.action,
        "subject": a.subject,
        "detail": a.detail,
        "hash": a.hash,
    }


def track_record(r: TrackRecord) -> dict[str, Any]:
    return {
        "logged": r.logged,
        "pending": r.pending,
        "scored": r.scored,
        "hits": r.hits,
        "hit_rate": r.hit_rate,
        "interval_low": r.interval_low,
        "interval_high": r.interval_high,
        "verdict": r.verdict.value,
        "minimum_for_verdict": r.minimum_for_verdict,
        "by_action": [
            {
                "action": a.action,
                "scored": a.scored,
                "hits": a.hits,
                "mean_forward_return": a.mean_forward_return,
            }
            for a in r.by_action
        ],
        "note": r.note,
        "method": (
            "Each logged recommendation is judged by the real price change over the next "
            "20 trading days. Moves under 0.5% and HOLD/WATCH calls are not scored. One entry "
            "per symbol, strategy and day. A past hit rate is not a forecast."
        ),
    }


def refresh_result(r: RefreshResult) -> dict[str, Any]:
    return {
        "evaluated": r.evaluated,
        "waiting": r.waiting,
        "unchecked_symbols": list(r.unchecked_symbols),
        "deferred_symbols": r.deferred_symbols,
        "notes": list(r.notes),
    }


def adaptation(v: AdaptationView) -> dict[str, Any]:
    return {
        "strategy": {"strategy_id": v.strategy.strategy_id, "name": v.strategy.name},
        "portfolio_id": v.portfolio_id,
        "proposals": [
            {
                "code": p.code,
                "kind": p.kind,
                "title": p.title,
                "rationale": p.rationale,
                "evidence": list(p.evidence),
                "change": p.change,
            }
            for p in v.report.proposals
        ],
        "notes": list(v.report.notes),
        "track_record": track_record(v.track_record),
        "explanation": explanation(v.explanation),
    }


def goal_review(v: GoalReview) -> dict[str, Any]:
    return {"report": goal_report(v.report), "explanation": explanation(v.explanation)}


# ------------------------------------------------------------------------ optional SLAI agents
def agent_status(a: AgentStatus) -> dict[str, Any]:
    return {
        "name": a.name,
        "label": a.label,
        "purpose": a.purpose,
        "enabled": a.enabled,
        "state": a.state,
        "detail": a.detail,
    }


def knowledge_answer(a: KnowledgeAnswer) -> dict[str, Any]:
    return {
        "status": a.status,
        "detail": a.detail,
        "passages": [
            {"source": p.source, "heading": p.heading, "text": p.text, "score": p.score}
            for p in a.passages
        ],
    }


def learning_share(r: LearningShare) -> dict[str, Any]:
    return {
        "status": r.status,
        "sent": r.sent,
        "duplicates": r.duplicates,
        "refused": r.refused,
        "detail": r.detail,
    }


def learning_recall(r: LearningRecall) -> dict[str, Any]:
    return {
        "status": r.status,
        "total": r.total,
        "detail": r.detail,
        "by_action": [
            {"action": a.action, "count": a.count, "mean_forward_return": a.mean_forward_return}
            for a in r.by_action
        ],
    }


def _allocation_stats(stats: Any) -> dict[str, Any] | None:
    if stats is None:
        return None
    return {
        "annual_volatility": stats.annual_volatility,
        "historical_annual_return": stats.historical_annual_return,
    }


def applied_allocation(r: Any) -> dict[str, Any]:
    return {
        "suggestion_id": r.suggestion_id,
        "filled": r.filled,
        "fees": d(r.fees),
        "orders": [
            {
                "symbol": o.symbol,
                "display": o.display,
                "side": o.side,
                "status": o.status,
                "detail": o.detail,
                "quantity": d(o.quantity),
                "price": d(o.price),
                "fee": d(o.fee),
            }
            for o in r.orders
        ],
        "simulated": True,
    }


def allocation(a: Any) -> dict[str, Any]:
    return {
        "status": a.status,
        "detail": a.detail,
        "portfolio_id": a.portfolio_id,
        "strategy_id": a.strategy_id,
        "focus": a.focus,
        "generated_at": t(a.generated_at) if a.generated_at else None,
        "solver": a.solver,
        "observations": a.observations,
        "window_start": a.window_start.isoformat() if a.window_start else None,
        "window_end": a.window_end.isoformat() if a.window_end else None,
        "cash_weight": a.cash_weight,
        "agent_notes": list(a.agent_notes),
        "suggestion_id": a.suggestion_id,
        "expires_at": t(a.expires_at) if a.expires_at else None,
        "fee_per_trade": d(a.fee_per_trade),
        "plan_notes": list(a.plan_notes),
        "current": _allocation_stats(a.current),
        "suggested": _allocation_stats(a.suggested),
        "lines": [
            {
                "symbol": line.symbol,
                "display": line.display,
                "current_weight": line.current_weight,
                "suggested_weight": line.suggested_weight,
                "change": line.change,
                "amount": d(line.amount) if line.amount is not None else None,
                "side": line.side,
            }
            for line in a.lines
        ],
        "excluded": [{"symbol": sym, "reason": why} for sym, why in a.excluded],
        "checks": [{"code": c.code, "ok": c.ok, "message": c.message} for c in a.checks],
        "basis": (
            "Historical statistics from real prices over the window shown. "
            "They describe the past and are not a forecast."
        ),
    }
