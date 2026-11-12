"""Machine-readable financial goals, constraints, preferences, and evaluations."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from math import isfinite

from slaifi.core.types import CurrencyCode
from slaifi.domain.assets import AssetClass
from slaifi.domain.utils.errors import DomainValidationError
from slaifi.domain.utils.helpers import require_aware_datetime, require_non_blank


class IncomePeriod(StrEnum):
    DAILY = "daily"  # per trading day; annualised with TRADING_DAYS_PER_YEAR
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
    """Desired annual return expressed as a fractional rate, not a guarantee."""

    annual_rate: float

    def __post_init__(self) -> None:
        if not isfinite(self.annual_rate) or self.annual_rate <= -1.0:
            raise DomainValidationError("annual return target must be finite and greater than -1")


@dataclass(frozen=True, slots=True)
class IncomeTarget:
    """Desired periodic portfolio income."""

    amount: Decimal
    period: IncomePeriod

    def __post_init__(self) -> None:
        if self.amount <= 0:
            raise DomainValidationError("income target amount must be positive")


@dataclass(frozen=True, slots=True)
class RiskConstraints:
    """Hard limits that a future strategy must not intentionally exceed."""

    max_drawdown_rate: float | None = None
    max_position_weight: float | None = None
    max_sector_weight: float | None = None
    max_leverage: float | None = None
    max_short_exposure: float | None = None
    allowed_asset_classes: frozenset[AssetClass] = frozenset()
    prohibited_asset_classes: frozenset[AssetClass] = frozenset()

    def __post_init__(self) -> None:
        bounded = {
            "max_drawdown_rate": self.max_drawdown_rate,
            "max_position_weight": self.max_position_weight,
            "max_sector_weight": self.max_sector_weight,
        }
        for name, value in bounded.items():
            if value is not None and (not isfinite(value) or not 0.0 <= value <= 1.0):
                raise DomainValidationError(f"{name} must be a finite rate in [0, 1]")
        if self.max_leverage is not None and (
            not isfinite(self.max_leverage) or self.max_leverage < 0.0
        ):
            raise DomainValidationError("max_leverage must be finite and non-negative")
        if self.max_short_exposure is not None and (
            not isfinite(self.max_short_exposure) or self.max_short_exposure < 0.0
        ):
            raise DomainValidationError("max_short_exposure must be finite and non-negative")
        overlap = self.allowed_asset_classes & self.prohibited_asset_classes
        if overlap:
            raise DomainValidationError("asset classes cannot be both allowed and prohibited")


@dataclass(frozen=True, slots=True)
class GoalPreferences:
    """Soft preferences that may guide future strategy selection."""

    dca_amount: Decimal | None = None
    cash_reserve: Decimal | None = None
    prefers_dividend_income: bool = False
    preferred_asset_classes: frozenset[AssetClass] = frozenset()

    def __post_init__(self) -> None:
        if self.dca_amount is not None and self.dca_amount < 0:
            raise DomainValidationError("dca_amount cannot be negative")
        if self.cash_reserve is not None and self.cash_reserve < 0:
            raise DomainValidationError("cash_reserve cannot be negative")


@dataclass(frozen=True, slots=True)
class FinancialGoal:
    """Composition of targets, constraints, and preferences."""

    goal_id: str
    return_target: ReturnTarget | None = None
    income_target: IncomeTarget | None = None
    constraints: RiskConstraints = RiskConstraints()
    preferences: GoalPreferences = GoalPreferences()

    def __post_init__(self) -> None:
        if not self.goal_id.strip():
            raise DomainValidationError("goal_id must not be empty")


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


# --------------------------------------------------------------------------------------------
# Measurable user goals (persisted objectives) and their evaluation results.
# Targets are objectives, never forecasts or guarantees.
# --------------------------------------------------------------------------------------------

TRADING_DAYS_PER_YEAR = 252  # explicit convention for per-trading-day targets
_RISK_TOLERANCES = ("conservative", "moderate", "aggressive")


class GoalBasis(StrEnum):
    """What the target measures."""

    REALIZED_PROFIT = "realized_profit"
    TOTAL_RETURN = "total_return"
    INVESTMENT_INCOME = "investment_income"
    TARGET_BALANCE = "target_balance"  # reach a portfolio value by a date
    SUSTAINABLE_WITHDRAWAL = "sustainable_withdrawal"  # fund regular withdrawals for N years


@dataclass(frozen=True, slots=True)
class GoalSpec:
    """A persisted, measurable financial objective."""

    goal_id: str
    name: str
    currency: CurrencyCode
    created_at: datetime
    basis: GoalBasis = GoalBasis.TOTAL_RETURN
    target_amount: Decimal | None = None
    period: IncomePeriod | None = None
    target_annual_rate: float | None = None
    horizon_years: float | None = None
    starting_capital: Decimal | None = None
    monthly_contribution: Decimal = Decimal("0")
    monthly_withdrawal: Decimal = Decimal("0")
    risk_tolerance: str | None = None
    max_acceptable_drawdown_rate: float | None = None
    portfolio_id: str | None = None
    # Balance to reach by ``horizon_years`` (basis TARGET_BALANCE).
    target_value: Decimal | None = None

    def __post_init__(self) -> None:
        require_non_blank(self.goal_id, name="goal_id")
        require_non_blank(self.name, name="goal name")
        require_aware_datetime(self.created_at, name="created_at")
        if not isinstance(self.currency, CurrencyCode):
            object.__setattr__(self, "currency", CurrencyCode(str(self.currency)))
        has_amount = self.target_amount is not None
        if has_amount and self.target_amount <= 0:  # type: ignore[operator]
            raise DomainValidationError("target_amount must be positive")
        if has_amount != (self.period is not None):
            raise DomainValidationError("target_amount and period must be supplied together")
        if self.target_annual_rate is not None and (
            not isfinite(self.target_annual_rate) or self.target_annual_rate <= -1.0
        ):
            raise DomainValidationError("target_annual_rate must be finite and greater than -1")
        if self.target_value is not None and self.target_value <= 0:
            raise DomainValidationError("target_value must be positive")
        if self.basis is GoalBasis.TARGET_BALANCE and (
            self.target_value is None or self.horizon_years is None
        ):
            raise DomainValidationError(
                "a target-balance goal needs the balance to reach and how many years you have"
            )
        if self.basis is GoalBasis.SUSTAINABLE_WITHDRAWAL and (
            self.monthly_withdrawal <= 0 or self.horizon_years is None
        ):
            raise DomainValidationError(
                "a withdrawal goal needs the monthly amount and how many years it must last"
            )
        needs_other_target = self.basis not in (
            GoalBasis.TARGET_BALANCE,
            GoalBasis.SUSTAINABLE_WITHDRAWAL,
        )
        if needs_other_target and not has_amount and self.target_annual_rate is None:
            raise DomainValidationError("a goal needs a target amount per period or a target rate")
        if self.horizon_years is not None and not (
            isfinite(self.horizon_years) and 0.0 < self.horizon_years <= 100.0
        ):
            raise DomainValidationError("horizon_years must be in (0, 100]")
        if self.starting_capital is not None and self.starting_capital < 0:
            raise DomainValidationError("starting_capital cannot be negative")
        if self.monthly_contribution < 0 or self.monthly_withdrawal < 0:
            raise DomainValidationError("contributions and withdrawals cannot be negative")
        if self.risk_tolerance is not None and self.risk_tolerance not in _RISK_TOLERANCES:
            raise DomainValidationError(f"risk_tolerance must be one of {_RISK_TOLERANCES}")
        if self.max_acceptable_drawdown_rate is not None and not (
            isfinite(self.max_acceptable_drawdown_rate)
            and 0.0 < self.max_acceptable_drawdown_rate <= 1.0
        ):
            raise DomainValidationError("max_acceptable_drawdown_rate must be in (0, 1]")


@dataclass(frozen=True, slots=True)
class GoalScenario:
    """One explicitly labelled hypothetical or user-assumed annual return scenario."""

    label: str
    annual_return_rate: float
    source: str  # user_assumption | hypothetical | historical_portfolio
    projected_value: Decimal | None
    period_profit: Decimal | None
    shortfall: Decimal | None
    meets_target: bool
    stress_loss: Decimal | None


@dataclass(frozen=True, slots=True)
class GoalFinding:
    code: str
    severity: str  # info | warning | critical
    message: str


@dataclass(frozen=True, slots=True)
class GoalProgress:
    """Measured (not projected) progress of a portfolio against a goal."""

    basis: GoalBasis
    window_label: str
    measured_amount: Decimal
    target_amount: Decimal | None
    progress_ratio: float | None
    on_track: bool | None
    detail: str


@dataclass(frozen=True, slots=True)
class GoalPlan:
    """Plan arithmetic for balance and withdrawal goals (all figures at the assumed rate)."""

    kind: str  # target_balance | sustainable_withdrawal
    basis_note: str  # what the figures were computed from, incl. any re-planning from today
    capital: Decimal
    years_used: float
    required_annual_return_rate: float | None = None
    required_monthly_contribution: Decimal | None = None
    projected_balance: Decimal | None = None
    balance_gap: Decimal | None = None
    months_capital_lasts: int | None = None
    lasts_beyond_100_years: bool = False
    sustainable_monthly_withdrawal: Decimal | None = None
    replanned_from_today: bool = False


@dataclass(frozen=True, slots=True)
class GoalFeasibilityReport:
    goal_id: str
    consistent: bool
    status: FeasibilityStatus
    capital_used: Decimal
    annual_target_amount: Decimal | None
    required_annual_return_rate: float | None
    required_capital_at_assumed_rate: Decimal | None
    assumed_annual_return_rate: float | None
    scenarios: tuple[GoalScenario, ...]
    findings: tuple[GoalFinding, ...]
    assumptions: tuple[str, ...]
    progress: GoalProgress | None = None
    plan: GoalPlan | None = None
