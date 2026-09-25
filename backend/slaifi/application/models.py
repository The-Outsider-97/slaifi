"""Structured application results combining calculations without conflating them."""

from dataclasses import dataclass
from typing import Mapping

from slaifi.application.contracts import ReasoningResult
from slaifi.domain.goals import IncomeGoalEvaluation, ReturnGoalEvaluation
from slaifi.domain.portfolio import PortfolioSnapshot
from slaifi.domain.risk import RiskStatistics


@dataclass(frozen=True, slots=True)
class TechnicalMeasurements:
    sma: float | None
    ema: float | None
    momentum: float | None
    rsi: float | None
    macd: float | None
    macd_signal: float | None
    atr: float | None


@dataclass(frozen=True, slots=True)
class MarketAnalysisResult:
    symbol: str
    observation_count: int
    latest_close: float
    simple_return: float | None
    rolling_volatility: float | None
    maximum_drawdown: float | None
    technical: TechnicalMeasurements
    features: Mapping[str, tuple[float | None, ...]]
    reasoning: ReasoningResult | None = None


@dataclass(frozen=True, slots=True)
class GoalEvaluationBundle:
    income: IncomeGoalEvaluation | None = None
    returns: ReturnGoalEvaluation | None = None


@dataclass(frozen=True, slots=True)
class PortfolioAnalysisResult:
    snapshot: PortfolioSnapshot
    risk: RiskStatistics | None
    goals: GoalEvaluationBundle | None
    reasoning: ReasoningResult | None = None
