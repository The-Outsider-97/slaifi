"""HTTP schemas for market and portfolio analysis use cases."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from slaifi.api.schemas.common import AssetInput, OHLCVBarInput, ReasoningResponse
from slaifi.api.schemas.goals import FinancialGoalInput, GoalEvaluationResponse
from slaifi.application.models import MarketAnalysisResult, PortfolioAnalysisResult
from slaifi.core.types import CurrencyCode
from slaifi.domain.portfolio import CashFlow, CashFlowKind, Portfolio, Trade, TradeSide


class MarketAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    asset: AssetInput
    bars: list[OHLCVBarInput] = Field(min_length=2)
    periods_per_year: int = Field(gt=0, le=1_000_000)
    moving_average_period: int = Field(default=20, gt=0)
    momentum_period: int = Field(default=10, gt=0)
    rsi_period: int = Field(default=14, gt=0)
    atr_period: int = Field(default=14, gt=0)
    reasoning_objective: str | None = Field(default=None, max_length=2000)


class TechnicalMeasurementsResponse(BaseModel):
    sma: float | None
    ema: float | None
    momentum: float | None
    rsi: float | None
    macd: float | None
    macd_signal: float | None
    atr: float | None


class MarketAnalysisResponse(BaseModel):
    symbol: str
    observation_count: int
    latest_close: float
    simple_return: float | None
    rolling_volatility: float | None
    maximum_drawdown: float | None
    technical: TechnicalMeasurementsResponse
    features: dict[str, list[float | None]]
    reasoning: ReasoningResponse | None

    @classmethod
    def from_application(cls, result: MarketAnalysisResult) -> "MarketAnalysisResponse":
        technical = result.technical
        return cls(
            symbol=result.symbol,
            observation_count=result.observation_count,
            latest_close=result.latest_close,
            simple_return=result.simple_return,
            rolling_volatility=result.rolling_volatility,
            maximum_drawdown=result.maximum_drawdown,
            technical=TechnicalMeasurementsResponse(
                sma=technical.sma,
                ema=technical.ema,
                momentum=technical.momentum,
                rsi=technical.rsi,
                macd=technical.macd,
                macd_signal=technical.macd_signal,
                atr=technical.atr,
            ),
            features={key: list(value) for key, value in result.features.items()},
            reasoning=(
                ReasoningResponse.from_application(result.reasoning)
                if result.reasoning is not None
                else None
            ),
        )


class TradeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    trade_id: str = Field(min_length=1, max_length=128)
    asset: AssetInput
    side: TradeSide
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(gt=0)
    fee: Decimal = Field(default=Decimal("0"), ge=0)
    occurred_at: datetime
    currency: str = Field(min_length=3, max_length=3)

    def to_domain(self) -> Trade:
        return Trade(
            trade_id=self.trade_id,
            asset=self.asset.to_domain(),
            side=self.side,
            quantity=self.quantity,
            unit_price=self.unit_price,
            fee=self.fee,
            occurred_at=self.occurred_at,
            currency=CurrencyCode(self.currency),
        )


class CashFlowInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    flow_id: str = Field(min_length=1, max_length=128)
    kind: CashFlowKind
    amount: Decimal = Field(gt=0)
    occurred_at: datetime
    currency: str = Field(min_length=3, max_length=3)
    asset: AssetInput | None = None

    def to_domain(self) -> CashFlow:
        return CashFlow(
            flow_id=self.flow_id,
            kind=self.kind,
            amount=self.amount,
            occurred_at=self.occurred_at,
            currency=CurrencyCode(self.currency),
            asset=self.asset.to_domain() if self.asset is not None else None,
        )


class PortfolioInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    portfolio_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    base_currency: str = Field(min_length=3, max_length=3)
    trades: list[TradeInput] = Field(default_factory=list)
    cash_flows: list[CashFlowInput] = Field(default_factory=list)

    def to_domain(self) -> Portfolio:
        return Portfolio(
            portfolio_id=self.portfolio_id,
            name=self.name,
            base_currency=CurrencyCode(self.base_currency),
            trades=tuple(item.to_domain() for item in self.trades),
            cash_flows=tuple(item.to_domain() for item in self.cash_flows),
        )


class AssetPriceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    asset: AssetInput
    price: Decimal = Field(gt=0)


class PortfolioAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    portfolio: PortfolioInput
    prices: list[AssetPriceInput]
    as_of: datetime
    initial_cash: Decimal = Decimal("0")
    returns: list[float] | None = None
    equity_values: list[float] | None = None
    periods_per_year: int | None = Field(default=None, gt=0, le=1_000_000)
    risk_free_annual_rate: float = Field(default=0.0, gt=-1.0)
    goal: FinancialGoalInput | None = None
    assumed_annual_return_rate: float | None = Field(default=None, gt=-1.0)
    assumed_annual_income_yield_rate: float | None = Field(default=None, ge=0.0)
    current_expected_annual_income: Decimal | None = Field(default=None, ge=0)
    reasoning_objective: str | None = Field(default=None, max_length=2000)


class PositionValuationResponse(BaseModel):
    asset: str
    quantity: Decimal
    average_cost: Decimal
    realized_pnl: Decimal
    market_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    portfolio_weight: float | None


class PortfolioSnapshotResponse(BaseModel):
    portfolio_id: str
    as_of: datetime
    base_currency: str
    cash_balance: Decimal
    securities_market_value: Decimal
    total_value: Decimal
    positions: list[PositionValuationResponse]


class RiskStatisticsResponse(BaseModel):
    observation_count: int
    periods_per_year: int
    annualized_volatility: float
    annualized_downside_deviation: float
    maximum_drawdown: float
    sharpe_ratio: float | None
    sortino_ratio: float | None
    concentration_hhi: float | None


class PortfolioAnalysisResponse(BaseModel):
    snapshot: PortfolioSnapshotResponse
    risk: RiskStatisticsResponse | None
    goals: GoalEvaluationResponse | None
    reasoning: ReasoningResponse | None

    @classmethod
    def from_application(
        cls,
        result: PortfolioAnalysisResult,
    ) -> "PortfolioAnalysisResponse":
        snapshot = result.snapshot
        return cls(
            snapshot=PortfolioSnapshotResponse(
                portfolio_id=snapshot.portfolio_id,
                as_of=snapshot.as_of,
                base_currency=str(snapshot.base_currency),
                cash_balance=snapshot.cash_balance,
                securities_market_value=snapshot.securities_market_value,
                total_value=snapshot.total_value,
                positions=[
                    PositionValuationResponse(
                        asset=item.position.asset.display_symbol,
                        quantity=item.position.quantity,
                        average_cost=item.position.average_cost,
                        realized_pnl=item.position.realized_pnl,
                        market_price=item.market_price,
                        market_value=item.market_value,
                        unrealized_pnl=item.unrealized_pnl,
                        portfolio_weight=item.portfolio_weight,
                    )
                    for item in snapshot.positions
                ],
            ),
            risk=(
                RiskStatisticsResponse(
                    observation_count=result.risk.observation_count,
                    periods_per_year=result.risk.periods_per_year,
                    annualized_volatility=result.risk.annualized_volatility,
                    annualized_downside_deviation=result.risk.annualized_downside_deviation,
                    maximum_drawdown=result.risk.maximum_drawdown,
                    sharpe_ratio=result.risk.sharpe_ratio,
                    sortino_ratio=result.risk.sortino_ratio,
                    concentration_hhi=result.risk.concentration_hhi,
                )
                if result.risk is not None
                else None
            ),
            goals=(
                GoalEvaluationResponse.from_application(result.goals)
                if result.goals is not None
                else None
            ),
            reasoning=(
                ReasoningResponse.from_application(result.reasoning)
                if result.reasoning is not None
                else None
            ),
        )
