"""Machine-readable financial goals, constraints, preferences, and evaluations."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from math import isfinite

from slaifi.core.exceptions import ValidationError
from slaifi.domain.assets import AssetClass


class IncomePeriod(StrEnum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"


class FeasibilityStatus(StrEnum):
    FEASIBLE_UNDER_ASSUMPTIONS = "feasible_under_assumptions"
    NOT_FEASIBLE_UNDER_ASSUMPTIONS = "not_feasible_under_assumptions"
    UNDETERMINED = "undetermined"


@dataclass(frozen=True, slots=True)
class ReturnTarget:
    annual_rate: float
    def __post_init__(self) -> None:
        if not isfinite(self.annual_rate) or self.annual_rate <= -1.0:
            raise ValidationError("annual return target must be finite and greater than -1")


@dataclass(frozen=True, slots=True)
class IncomeTarget:
    amount: Decimal
    period: IncomePeriod
    def __post_init__(self) -> None:
        if self.amount <= 0: raise ValidationError("income target amount must be positive")


@dataclass(frozen=True, slots=True)
class RiskConstraints:
    max_drawdown_rate: float | None = None
    max_position_weight: float | None = None
    max_sector_weight: float | None = None
    max_leverage: float | None = None
    max_short_exposure: float | None = None
    allowed_asset_classes: frozenset[AssetClass] = frozenset()
    prohibited_asset_classes: frozenset[AssetClass] = frozenset()
    def __post_init__(self) -> None:
        for name, value in {"max_drawdown_rate": self.max_drawdown_rate, "max_position_weight": self.max_position_weight, "max_sector_weight": self.max_sector_weight}.items():
            if value is not None and (not isfinite(value) or not 0.0 <= value <= 1.0): raise ValidationError(f"{name} must be a finite rate in [0, 1]")
        if self.max_leverage is not None and (not isfinite(self.max_leverage) or self.max_leverage < 0): raise ValidationError("max_leverage must be finite and non-negative")
        if self.max_short_exposure is not None and (not isfinite(self.max_short_exposure) or self.max_short_exposure < 0): raise ValidationError("max_short_exposure must be finite and non-negative")
        if self.allowed_asset_classes & self.prohibited_asset_classes: raise ValidationError("asset classes cannot be both allowed and prohibited")


@dataclass(frozen=True, slots=True)
class GoalPreferences:
    dca_amount: Decimal | None = None
    cash_reserve: Decimal | None = None
    prefers_dividend_income: bool = False
    preferred_asset_classes: frozenset[AssetClass] = frozenset()
    def __post_init__(self) -> None:
        if self.dca_amount is not None and self.dca_amount < 0: raise ValidationError("dca_amount cannot be negative")
        if self.cash_reserve is not None and self.cash_reserve < 0: raise ValidationError("cash_reserve cannot be negative")


@dataclass(frozen=True, slots=True)
class FinancialGoal:
    goal_id: str
    return_target: ReturnTarget | None = None
    income_target: IncomeTarget | None = None
    constraints: RiskConstraints = RiskConstraints()
    preferences: GoalPreferences = GoalPreferences()
    def __post_init__(self) -> None:
        if not self.goal_id.strip(): raise ValidationError("goal_id must not be empty")


@dataclass(frozen=True, slots=True)
class IncomeGoalEvaluation:
    annual_income_target: Decimal
    available_capital: Decimal
    required_yield_rate: float | None
    assumed_annual_yield_rate: float | None
    required_capital_at_assumed_yield: Decimal | None
    expected_annual_income: Decimal | None
    annual_income_shortfall: Decimal | None
    status: FeasibilityStatus


@dataclass(frozen=True, slots=True)
class ReturnGoalEvaluation:
    target_annual_rate: float
    assumed_annual_rate: float | None
    annual_rate_gap: float | None
    status: FeasibilityStatus
