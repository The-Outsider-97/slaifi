"""HTTP schemas for financial goals and feasibility evaluations."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from slaifi.api.schemas.common import ReasoningResponse
from slaifi.application.models import GoalAnalysisResult, GoalEvaluationBundle
from slaifi.domain.assets import AssetClass
from slaifi.domain.goals import (
    FinancialGoal,
    GoalPreferences,
    IncomePeriod,
    IncomeTarget,
    ReturnTarget,
    RiskConstraints,
)


class ReturnTargetInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    annual_rate: float = Field(gt=-1.0)


class IncomeTargetInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    amount: Decimal = Field(gt=0)
    period: IncomePeriod


class RiskConstraintsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_drawdown_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    max_position_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    max_sector_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    max_leverage: float | None = Field(default=None, ge=0.0)
    max_short_exposure: float | None = Field(default=None, ge=0.0)
    allowed_asset_classes: set[AssetClass] = Field(default_factory=set)
    prohibited_asset_classes: set[AssetClass] = Field(default_factory=set)


class GoalPreferencesInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dca_amount: Decimal | None = Field(default=None, ge=0)
    cash_reserve: Decimal | None = Field(default=None, ge=0)
    prefers_dividend_income: bool = False
    preferred_asset_classes: set[AssetClass] = Field(default_factory=set)


class FinancialGoalInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    goal_id: str = Field(min_length=1, max_length=128)
    return_target: ReturnTargetInput | None = None
    income_target: IncomeTargetInput | None = None
    constraints: RiskConstraintsInput = Field(default_factory=RiskConstraintsInput)
    preferences: GoalPreferencesInput = Field(default_factory=GoalPreferencesInput)

    def to_domain(self) -> FinancialGoal:
        return FinancialGoal(
            goal_id=self.goal_id,
            return_target=(
                ReturnTarget(self.return_target.annual_rate)
                if self.return_target is not None
                else None
            ),
            income_target=(
                IncomeTarget(self.income_target.amount, self.income_target.period)
                if self.income_target is not None
                else None
            ),
            constraints=RiskConstraints(
                max_drawdown_rate=self.constraints.max_drawdown_rate,
                max_position_weight=self.constraints.max_position_weight,
                max_sector_weight=self.constraints.max_sector_weight,
                max_leverage=self.constraints.max_leverage,
                max_short_exposure=self.constraints.max_short_exposure,
                allowed_asset_classes=frozenset(self.constraints.allowed_asset_classes),
                prohibited_asset_classes=frozenset(
                    self.constraints.prohibited_asset_classes
                ),
            ),
            preferences=GoalPreferences(
                dca_amount=self.preferences.dca_amount,
                cash_reserve=self.preferences.cash_reserve,
                prefers_dividend_income=self.preferences.prefers_dividend_income,
                preferred_asset_classes=frozenset(
                    self.preferences.preferred_asset_classes
                ),
            ),
        )


class IncomeGoalEvaluationResponse(BaseModel):
    annual_income_target: Decimal
    available_capital: Decimal
    required_yield_rate: float | None
    assumed_annual_yield_rate: float | None
    required_capital_at_assumed_yield: Decimal | None
    expected_annual_income: Decimal | None
    annual_income_shortfall: Decimal | None
    status: str


class ReturnGoalEvaluationResponse(BaseModel):
    target_annual_rate: float
    assumed_annual_rate: float | None
    annual_rate_gap: float | None
    status: str


class GoalEvaluationResponse(BaseModel):
    """Authoritative deterministic goal arithmetic only."""

    income: IncomeGoalEvaluationResponse | None
    returns: ReturnGoalEvaluationResponse | None

    @classmethod
    def from_application(cls, bundle: GoalEvaluationBundle) -> "GoalEvaluationResponse":
        income = None
        if bundle.income is not None:
            item = bundle.income
            income = IncomeGoalEvaluationResponse(
                annual_income_target=item.annual_income_target,
                available_capital=item.available_capital,
                required_yield_rate=item.required_yield_rate,
                assumed_annual_yield_rate=item.assumed_annual_yield_rate,
                required_capital_at_assumed_yield=item.required_capital_at_assumed_yield,
                expected_annual_income=item.expected_annual_income,
                annual_income_shortfall=item.annual_income_shortfall,
                status=item.status.value,
            )
        returns = None
        if bundle.returns is not None:
            item = bundle.returns
            returns = ReturnGoalEvaluationResponse(
                target_annual_rate=item.target_annual_rate,
                assumed_annual_rate=item.assumed_annual_rate,
                annual_rate_gap=item.annual_rate_gap,
                status=item.status.value,
            )
        return cls(income=income, returns=returns)


class EvaluateGoalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    goal: FinancialGoalInput
    available_capital: Decimal = Field(ge=0)
    assumed_annual_return_rate: float | None = Field(default=None, gt=-1.0)
    assumed_annual_income_yield_rate: float | None = Field(default=None, ge=0.0)
    current_expected_annual_income: Decimal | None = Field(default=None, ge=0)
    reasoning_objective: str | None = Field(default=None, max_length=2000)


class GoalAnalysisResponse(BaseModel):
    """Goal calculations plus optional, clearly separate SLAI interpretation."""

    evaluation: GoalEvaluationResponse
    reasoning: ReasoningResponse | None

    @classmethod
    def from_application(cls, result: GoalAnalysisResult) -> "GoalAnalysisResponse":
        return cls(
            evaluation=GoalEvaluationResponse.from_application(result.evaluation),
            reasoning=(
                ReasoningResponse.from_application(result.reasoning)
                if result.reasoning is not None
                else None
            ),
        )
