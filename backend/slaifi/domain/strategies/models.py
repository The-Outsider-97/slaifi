"""Investment strategy profiles: explicit, configurable financial parameters.

A strategy never contains vague personality labels. Presets ("hawkish", "care-bear") are only
named starting points that initialise the numeric parameters below; every parameter can be
changed afterwards. Hard limits (``constraints`` and ``excluded_symbols``) take precedence over
every optimisation preference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from math import isfinite

from slaifi.domain.assets import AssetClass
from slaifi.domain.goals import RiskConstraints
from slaifi.domain.utils import DomainValidationError, require_non_blank


class RiskTolerance(StrEnum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class InvestmentHorizon(StrEnum):
    """Coarse horizon bucket derived from the user's actual horizon in days."""

    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class TradingFrequency(StrEnum):
    LOW = "low"  # roughly monthly or less
    MEDIUM = "medium"  # roughly weekly
    HIGH = "high"  # daily / opportunistic


SHORT_HORIZON_MAX_DAYS = 90
MEDIUM_HORIZON_MAX_DAYS = 730


def classify_horizon(horizon_days: int) -> InvestmentHorizon:
    if horizon_days <= SHORT_HORIZON_MAX_DAYS:
        return InvestmentHorizon.SHORT
    if horizon_days <= MEDIUM_HORIZON_MAX_DAYS:
        return InvestmentHorizon.MEDIUM
    return InvestmentHorizon.LONG


@dataclass(frozen=True, slots=True)
class TransactionCosts:
    """Assumed trading frictions, as fractions of notional (``0.0005`` = 5 bps).

    The flat fee per trade and per withdrawal belongs to the trading platform, not to a strategy
    (see ``PlatformFees``), so the default proportional commission is zero.
    """

    commission_rate: Decimal = Decimal("0")
    commission_minimum: Decimal = Decimal("0")
    slippage_rate: Decimal = Decimal("0.0005")

    def __post_init__(self) -> None:
        for name, value in (
            ("commission_rate", self.commission_rate),
            ("commission_minimum", self.commission_minimum),
            ("slippage_rate", self.slippage_rate),
        ):
            if value < 0:
                raise DomainValidationError(f"{name} cannot be negative")
        if self.commission_rate >= 1 or self.slippage_rate >= 1:
            raise DomainValidationError("commission and slippage rates must be below 100%")


@dataclass(frozen=True, slots=True)
class StrategyProfile:
    strategy_id: str
    name: str
    risk_tolerance: RiskTolerance
    horizon_days: int
    constraints: RiskConstraints = field(default_factory=RiskConstraints)
    preset: str | None = None
    max_concentration_hhi: float | None = None
    cash_reserve_rate: float = 0.0
    max_annualized_volatility: float | None = None
    preferred_asset_classes: frozenset[AssetClass] = frozenset()
    excluded_symbols: frozenset[str] = frozenset()
    trading_frequency: TradingFrequency = TradingFrequency.LOW
    costs: TransactionCosts = field(default_factory=TransactionCosts)
    reinvest_dividends: bool = True
    # 0.0 = pure capital growth priority, 1.0 = pure income priority.
    income_weight: float = 0.0
    # Capital the strategy is meant to deploy when no portfolio is attached (goal arithmetic).
    capital: Decimal | None = None

    def __post_init__(self) -> None:
        require_non_blank(self.strategy_id, name="strategy_id")
        require_non_blank(self.name, name="strategy name")
        if not 1 <= self.horizon_days <= 36_500:
            raise DomainValidationError("horizon_days must be between 1 and 36500")
        if not isfinite(self.cash_reserve_rate) or not 0.0 <= self.cash_reserve_rate < 1.0:
            raise DomainValidationError("cash_reserve_rate must be in [0, 1)")
        if self.max_concentration_hhi is not None and (
            not isfinite(self.max_concentration_hhi) or not 0.0 < self.max_concentration_hhi <= 1.0
        ):
            raise DomainValidationError("max_concentration_hhi must be in (0, 1]")
        if self.max_annualized_volatility is not None and (
            not isfinite(self.max_annualized_volatility) or self.max_annualized_volatility <= 0.0
        ):
            raise DomainValidationError("max_annualized_volatility must be positive")
        if self.capital is not None and self.capital < 0:
            raise DomainValidationError("capital cannot be negative")
        if not isfinite(self.income_weight) or not 0.0 <= self.income_weight <= 1.0:
            raise DomainValidationError("income_weight must be in [0, 1]")
        position_cap = self.constraints.max_position_weight
        if position_cap is not None and position_cap <= 0.0:
            raise DomainValidationError("max_position_weight must be greater than zero")
        object.__setattr__(
            self,
            "excluded_symbols",
            frozenset(symbol.strip().upper() for symbol in self.excluded_symbols if symbol.strip()),
        )

    @property
    def horizon(self) -> InvestmentHorizon:
        return classify_horizon(self.horizon_days)

    @property
    def max_position_weight(self) -> float | None:
        return self.constraints.max_position_weight

    @property
    def max_drawdown_rate(self) -> float | None:
        return self.constraints.max_drawdown_rate
