"""Field-level strategy edits shared by the Strategies UI and the SLAI advisor.

One implementation of "how a field is read, validated, applied and judged" keeps the two
entry points from drifting apart. Hard limits are the fields that block orders; changing one is
always reported, and *loosening* one requires explicit acknowledgement.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from typing import Any

from slaifi.core.utils.errors import ValidationError
from slaifi.domain.assets import AssetClass
from slaifi.domain.goals import RiskConstraints
from slaifi.domain.strategies import (
    RiskTolerance,
    StrategyProfile,
    TradingFrequency,
    TransactionCosts,
)

HARD_LIMIT_FIELDS = frozenset(
    {
        "max_position_weight",
        "max_drawdown_rate",
        "max_short_exposure",
        "cash_reserve_rate",
        "max_annualized_volatility",
        "max_concentration_hhi",
        "excluded_symbols",
        "prohibited_asset_classes",
        "allowed_asset_classes",
    }
)
EDITABLE_FIELDS = frozenset(
    {
        "name",
        "risk_tolerance",
        "horizon_days",
        "capital",
        "preferred_asset_classes",
        "trading_frequency",
        "income_weight",
        "commission_rate",
        "commission_minimum",
        "slippage_rate",
        "reinvest_dividends",
    }
    | HARD_LIMIT_FIELDS
)
_RISK_ORDER = {"conservative": 0, "moderate": 1, "aggressive": 2}


def current_value(strategy: StrategyProfile, field: str) -> Any:
    c = strategy.constraints
    values: dict[str, Any] = {
        "name": strategy.name,
        "risk_tolerance": strategy.risk_tolerance.value,
        "horizon_days": strategy.horizon_days,
        "capital": str(strategy.capital) if strategy.capital is not None else None,
        "max_position_weight": c.max_position_weight,
        "max_drawdown_rate": c.max_drawdown_rate,
        "max_short_exposure": c.max_short_exposure,
        "cash_reserve_rate": strategy.cash_reserve_rate,
        "max_annualized_volatility": strategy.max_annualized_volatility,
        "max_concentration_hhi": strategy.max_concentration_hhi,
        "excluded_symbols": sorted(strategy.excluded_symbols),
        "prohibited_asset_classes": sorted(a.value for a in c.prohibited_asset_classes),
        "allowed_asset_classes": sorted(a.value for a in c.allowed_asset_classes),
        "preferred_asset_classes": sorted(a.value for a in strategy.preferred_asset_classes),
        "trading_frequency": strategy.trading_frequency.value,
        "income_weight": strategy.income_weight,
        "commission_rate": str(strategy.costs.commission_rate),
        "commission_minimum": str(strategy.costs.commission_minimum),
        "slippage_rate": str(strategy.costs.slippage_rate),
        "reinvest_dividends": strategy.reinvest_dividends,
    }
    if field not in values:
        raise ValidationError(f"unknown strategy field {field!r}")
    return values[field]


def _classes(value: Any) -> frozenset[AssetClass]:
    try:
        return frozenset(AssetClass(str(v)) for v in (value or []))
    except ValueError as exc:
        raise ValidationError(f"unknown asset class in {value!r}") from exc


def _dec(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValidationError(f"{field} must be a number") from exc
    if not result.is_finite():
        raise ValidationError(f"{field} must be finite")
    return result


def apply_changes(strategy: StrategyProfile, changes: Mapping[str, Any]) -> StrategyProfile:
    """Return a new validated strategy with ``changes`` applied. Unknown fields are rejected."""

    try:
        return _apply_changes(strategy, changes)
    except (TypeError, ValueError) as exc:
        # e.g. a non-numeric string for a numeric field: a clear 422, never a server error.
        raise ValidationError(f"a value was not in the expected form ({exc})") from exc


def _apply_changes(strategy: StrategyProfile, changes: Mapping[str, Any]) -> StrategyProfile:

    unknown = set(changes) - EDITABLE_FIELDS
    if unknown:
        raise ValidationError(f"cannot change: {', '.join(sorted(unknown))}")
    constraint_kwargs: dict[str, Any] = {}
    kwargs: dict[str, Any] = {}
    costs: dict[str, Decimal] = {}
    for field, value in changes.items():
        if field == "name":
            kwargs["name"] = str(value)
        elif field == "risk_tolerance":
            try:
                kwargs["risk_tolerance"] = RiskTolerance(str(value))
            except ValueError as exc:
                raise ValidationError(
                    "risk_tolerance must be conservative, moderate or aggressive"
                ) from exc
        elif field == "horizon_days":
            kwargs["horizon_days"] = int(value)
        elif field == "capital":
            kwargs["capital"] = None if value in (None, "") else _dec(value, field)
        elif field in {"max_position_weight", "max_drawdown_rate"}:
            constraint_kwargs[field] = None if value is None else float(value)
        elif field == "max_short_exposure":
            # 0 (or empty) switches short selling off; the domain rejects values outside [0, 1].
            constraint_kwargs[field] = 0.0 if value in (None, "") else float(value)
        elif field == "prohibited_asset_classes" or field == "allowed_asset_classes":
            constraint_kwargs[field] = _classes(value)
        elif field == "cash_reserve_rate":
            kwargs["cash_reserve_rate"] = float(value or 0.0)
        elif field in {"max_annualized_volatility", "max_concentration_hhi"}:
            kwargs[field] = None if value is None else float(value)
        elif field == "excluded_symbols":
            kwargs["excluded_symbols"] = frozenset(
                str(v).strip().upper() for v in (value or []) if str(v).strip()
            )
        elif field == "preferred_asset_classes":
            kwargs["preferred_asset_classes"] = _classes(value)
        elif field == "trading_frequency":
            try:
                kwargs["trading_frequency"] = TradingFrequency(str(value))
            except ValueError as exc:
                raise ValidationError("trading_frequency must be low, medium or high") from exc
        elif field == "income_weight":
            kwargs["income_weight"] = float(value)
        elif field in {"commission_rate", "commission_minimum", "slippage_rate"}:
            costs[field] = _dec(value, field)
        elif field == "reinvest_dividends":
            kwargs["reinvest_dividends"] = bool(value)
    if constraint_kwargs:
        kwargs["constraints"] = replace(strategy.constraints, **constraint_kwargs)
    if costs:
        kwargs["costs"] = TransactionCosts(
            commission_rate=costs.get("commission_rate", strategy.costs.commission_rate),
            commission_minimum=costs.get("commission_minimum", strategy.costs.commission_minimum),
            slippage_rate=costs.get("slippage_rate", strategy.costs.slippage_rate),
        )
    try:
        # A preset name stops describing the strategy once its numbers have been edited.
        updated = replace(strategy, preset=None if kwargs or costs else strategy.preset, **kwargs)
        if not kwargs and not costs:
            updated = strategy
        return updated
    except (TypeError, ValueError) as exc:
        raise ValidationError(str(exc)) from exc


def is_loosening(field: str, old: Any, new: Any) -> bool:
    """True when the change makes a hard limit less restrictive (or removes it)."""

    if field not in HARD_LIMIT_FIELDS:
        return False
    if field == "max_short_exposure":
        # More short exposure is less restrictive; 0 means shorting is off.
        return float(new or 0.0) > float(old or 0.0)
    if field in {
        "max_position_weight",
        "max_drawdown_rate",
        "max_annualized_volatility",
        "max_concentration_hhi",
    }:
        if old is None:
            return False
        return new is None or float(new) > float(old)
    if field == "cash_reserve_rate":
        return float(new or 0.0) < float(old or 0.0)
    if field in {"excluded_symbols", "prohibited_asset_classes"}:
        return bool(set(old or []) - set(new or []))
    if field == "allowed_asset_classes":
        # An empty allow-list means "everything"; widening or clearing the list loosens it.
        if not old:
            return False
        return not new or bool(set(new) - set(old))
    return False


def describe_change(field: str, old: Any, new: Any) -> str:
    labels = {
        "max_position_weight": "Maximum position size",
        "max_drawdown_rate": "Maximum drawdown",
        "max_short_exposure": "Largest short exposure",
        "cash_reserve_rate": "Cash reserve",
        "max_annualized_volatility": "Volatility cap",
        "max_concentration_hhi": "Concentration (HHI) limit",
        "excluded_symbols": "Excluded symbols",
        "prohibited_asset_classes": "Prohibited asset classes",
        "allowed_asset_classes": "Allowed asset classes",
        "preferred_asset_classes": "Preferred asset classes",
        "risk_tolerance": "Risk tolerance",
        "horizon_days": "Horizon (days)",
        "trading_frequency": "Trading frequency",
        "income_weight": "Income weight",
        "commission_rate": "Commission rate",
        "slippage_rate": "Slippage rate",
        "commission_minimum": "Minimum commission",
        "reinvest_dividends": "Reinvest dividends",
        "capital": "Strategy capital",
        "name": "Name",
    }
    pct = {
        "max_position_weight",
        "max_drawdown_rate",
        "max_short_exposure",
        "cash_reserve_rate",
        "max_annualized_volatility",
    }

    def fmt(value: Any) -> str:
        if value is None or value == [] or value == "":
            return "none"
        if field in pct and isinstance(value, (int, float)):
            return f"{float(value):.1%}"
        if isinstance(value, list):
            return ", ".join(str(v) for v in value)
        return str(value)

    return f"{labels.get(field, field)}: {fmt(old)} → {fmt(new)}"


def risk_direction(old: Any, new: Any) -> int:
    """+1 more aggressive, -1 more conservative, 0 unchanged (for explanations)."""

    return (_RISK_ORDER.get(str(new), 0) > _RISK_ORDER.get(str(old), 0)) - (
        _RISK_ORDER.get(str(new), 0) < _RISK_ORDER.get(str(old), 0)
    )


__all__ = [
    "EDITABLE_FIELDS",
    "HARD_LIMIT_FIELDS",
    "apply_changes",
    "current_value",
    "describe_change",
    "is_loosening",
    "risk_direction",
    "RiskConstraints",
]
