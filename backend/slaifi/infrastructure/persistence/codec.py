"""JSON codecs between domain objects and SQLite text columns. Decimals are stored as strings."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from slaifi.core.types import CurrencyCode
from slaifi.domain.assets import AssetClass, AssetId
from slaifi.domain.goals import GoalBasis, GoalSpec, IncomePeriod, RiskConstraints
from slaifi.domain.learning import RecommendationOutcome, RecommendationRecord
from slaifi.domain.paper import ExecutionDetails
from slaifi.domain.strategies import (
    RiskTolerance,
    StrategyProfile,
    TradingFrequency,
    TransactionCosts,
)


def dt_to_text(value: datetime) -> str:
    return value.isoformat()


def dt_from_text(value: str) -> datetime:
    return datetime.fromisoformat(value)


def asset_to_dict(asset: AssetId) -> dict[str, Any]:
    return {
        "symbol": asset.symbol,
        "asset_class": asset.asset_class.value,
        "exchange": asset.exchange,
        "currency": str(asset.currency) if asset.currency is not None else None,
        "instrument_id": asset.instrument_id,
    }


def asset_from_dict(data: dict[str, Any]) -> AssetId:
    return AssetId(
        symbol=data["symbol"],
        asset_class=AssetClass(data.get("asset_class") or "unknown"),
        exchange=data.get("exchange"),
        currency=CurrencyCode(data["currency"]) if data.get("currency") else None,
        instrument_id=data.get("instrument_id"),
    )


def strategy_to_dict(strategy: StrategyProfile) -> dict[str, Any]:
    c = strategy.constraints
    return {
        "strategy_id": strategy.strategy_id,
        "name": strategy.name,
        "preset": strategy.preset,
        "risk_tolerance": strategy.risk_tolerance.value,
        "horizon_days": strategy.horizon_days,
        "constraints": {
            "max_drawdown_rate": c.max_drawdown_rate,
            "max_position_weight": c.max_position_weight,
            "max_sector_weight": c.max_sector_weight,
            "max_leverage": c.max_leverage,
            "max_short_exposure": c.max_short_exposure,
            "allowed_asset_classes": sorted(a.value for a in c.allowed_asset_classes),
            "prohibited_asset_classes": sorted(a.value for a in c.prohibited_asset_classes),
        },
        "max_concentration_hhi": strategy.max_concentration_hhi,
        "cash_reserve_rate": strategy.cash_reserve_rate,
        "max_annualized_volatility": strategy.max_annualized_volatility,
        "preferred_asset_classes": sorted(a.value for a in strategy.preferred_asset_classes),
        "excluded_symbols": sorted(strategy.excluded_symbols),
        "trading_frequency": strategy.trading_frequency.value,
        "costs": {
            "commission_rate": str(strategy.costs.commission_rate),
            "commission_minimum": str(strategy.costs.commission_minimum),
            "slippage_rate": str(strategy.costs.slippage_rate),
        },
        "reinvest_dividends": strategy.reinvest_dividends,
        "income_weight": strategy.income_weight,
        "capital": str(strategy.capital) if strategy.capital is not None else None,
    }


def strategy_from_dict(data: dict[str, Any]) -> StrategyProfile:
    c = data.get("constraints") or {}
    costs = data.get("costs") or {}
    return StrategyProfile(
        strategy_id=data["strategy_id"],
        name=data["name"],
        preset=data.get("preset"),
        risk_tolerance=RiskTolerance(data["risk_tolerance"]),
        horizon_days=int(data["horizon_days"]),
        constraints=RiskConstraints(
            max_drawdown_rate=c.get("max_drawdown_rate"),
            max_position_weight=c.get("max_position_weight"),
            max_sector_weight=c.get("max_sector_weight"),
            max_leverage=c.get("max_leverage"),
            max_short_exposure=c.get("max_short_exposure"),
            allowed_asset_classes=frozenset(
                AssetClass(v) for v in c.get("allowed_asset_classes", [])
            ),
            prohibited_asset_classes=frozenset(
                AssetClass(v) for v in c.get("prohibited_asset_classes", [])
            ),
        ),
        max_concentration_hhi=data.get("max_concentration_hhi"),
        cash_reserve_rate=float(data.get("cash_reserve_rate") or 0.0),
        max_annualized_volatility=data.get("max_annualized_volatility"),
        preferred_asset_classes=frozenset(
            AssetClass(v) for v in data.get("preferred_asset_classes", [])
        ),
        excluded_symbols=frozenset(data.get("excluded_symbols", [])),
        trading_frequency=TradingFrequency(data.get("trading_frequency", "low")),
        costs=TransactionCosts(
            commission_rate=Decimal(costs.get("commission_rate", "0")),
            commission_minimum=Decimal(costs.get("commission_minimum", "0")),
            slippage_rate=Decimal(costs.get("slippage_rate", "0.0005")),
        ),
        reinvest_dividends=bool(data.get("reinvest_dividends", True)),
        income_weight=float(data.get("income_weight") or 0.0),
        capital=Decimal(data["capital"]) if data.get("capital") else None,
    )


def goal_to_dict(goal: GoalSpec) -> dict[str, Any]:
    return {
        "goal_id": goal.goal_id,
        "name": goal.name,
        "currency": str(goal.currency),
        "created_at": dt_to_text(goal.created_at),
        "basis": goal.basis.value,
        "target_amount": str(goal.target_amount) if goal.target_amount is not None else None,
        "period": goal.period.value if goal.period is not None else None,
        "target_annual_rate": goal.target_annual_rate,
        "horizon_years": goal.horizon_years,
        "starting_capital": str(goal.starting_capital)
        if goal.starting_capital is not None
        else None,
        "monthly_contribution": str(goal.monthly_contribution),
        "monthly_withdrawal": str(goal.monthly_withdrawal),
        "risk_tolerance": goal.risk_tolerance,
        "max_acceptable_drawdown_rate": goal.max_acceptable_drawdown_rate,
        "portfolio_id": goal.portfolio_id,
        "target_value": str(goal.target_value) if goal.target_value is not None else None,
    }


def goal_from_dict(data: dict[str, Any]) -> GoalSpec:
    return GoalSpec(
        goal_id=data["goal_id"],
        name=data["name"],
        currency=CurrencyCode(data["currency"]),
        created_at=dt_from_text(data["created_at"]),
        basis=GoalBasis(data["basis"]),
        target_amount=Decimal(data["target_amount"]) if data.get("target_amount") else None,
        period=IncomePeriod(data["period"]) if data.get("period") else None,
        target_annual_rate=data.get("target_annual_rate"),
        horizon_years=data.get("horizon_years"),
        starting_capital=Decimal(data["starting_capital"])
        if data.get("starting_capital")
        else None,
        monthly_contribution=Decimal(data.get("monthly_contribution") or "0"),
        monthly_withdrawal=Decimal(data.get("monthly_withdrawal") or "0"),
        risk_tolerance=data.get("risk_tolerance"),
        max_acceptable_drawdown_rate=data.get("max_acceptable_drawdown_rate"),
        portfolio_id=data.get("portfolio_id"),
        target_value=Decimal(data["target_value"]) if data.get("target_value") else None,
    )


def execution_to_dict(details: ExecutionDetails) -> dict[str, Any]:
    return {
        "quote_price": str(details.quote_price),
        "execution_price": str(details.execution_price),
        "slippage_per_unit": str(details.slippage_per_unit),
        "commission": str(details.commission),
        "gross_amount": str(details.gross_amount),
        "net_cash_effect": str(details.net_cash_effect),
        "currency": str(details.currency),
        "quote_observed_at": dt_to_text(details.quote_observed_at),
        "quote_source": details.quote_source,
        "data_mode": details.data_mode,
        "executed_at": dt_to_text(details.executed_at),
        "market_open": details.market_open,
        "notes": list(details.notes),
    }


def execution_from_dict(data: dict[str, Any]) -> ExecutionDetails:
    return ExecutionDetails(
        quote_price=Decimal(data["quote_price"]),
        execution_price=Decimal(data["execution_price"]),
        slippage_per_unit=Decimal(data["slippage_per_unit"]),
        commission=Decimal(data["commission"]),
        gross_amount=Decimal(data["gross_amount"]),
        net_cash_effect=Decimal(data["net_cash_effect"]),
        currency=CurrencyCode(data["currency"]),
        quote_observed_at=dt_from_text(data["quote_observed_at"]),
        quote_source=data["quote_source"],
        data_mode=data["data_mode"],
        executed_at=dt_from_text(data["executed_at"]),
        market_open=data.get("market_open"),
        notes=tuple(data.get("notes", ())),
    )


def recommendation_to_dict(record: RecommendationRecord) -> dict[str, Any]:
    return {
        "record_id": record.record_id,
        "symbol": record.symbol,
        "exchange": record.exchange,
        "asset_class": record.asset_class,
        "action": record.action,
        "signal_score": record.signal_score,
        "strategy_id": record.strategy_id,
        "issued_at": dt_to_text(record.issued_at),
        "reference_price": str(record.reference_price),
        "horizon_trading_days": record.horizon_trading_days,
    }


def recommendation_from_dict(data: dict[str, Any]) -> RecommendationRecord:
    return RecommendationRecord(
        record_id=data["record_id"],
        symbol=data["symbol"],
        exchange=data.get("exchange"),
        asset_class=data["asset_class"],
        action=data["action"],
        signal_score=data.get("signal_score"),
        strategy_id=data["strategy_id"],
        issued_at=dt_from_text(data["issued_at"]),
        reference_price=Decimal(data["reference_price"]),
        horizon_trading_days=int(data["horizon_trading_days"]),
    )


def outcome_to_dict(outcome: RecommendationOutcome) -> dict[str, Any]:
    return {
        "record_id": outcome.record_id,
        "evaluated_at": dt_to_text(outcome.evaluated_at),
        "end_price": str(outcome.end_price),
        "forward_return": outcome.forward_return,
        "correct": outcome.correct,
        "data_source": outcome.data_source,
    }


def outcome_from_dict(data: dict[str, Any]) -> RecommendationOutcome:
    return RecommendationOutcome(
        record_id=data["record_id"],
        evaluated_at=dt_from_text(data["evaluated_at"]),
        end_price=Decimal(data["end_price"]),
        forward_return=float(data["forward_return"]),
        correct=data.get("correct"),
        data_source=data.get("data_source", ""),
    )
