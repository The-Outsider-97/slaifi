"""Portfolio-analysis application orchestration."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal

from slaifi.application.contracts import FinancialReasoner, ReasoningRequest
from slaifi.application.models import GoalEvaluationBundle, PortfolioAnalysisResult
from slaifi.core.exceptions import ValidationError
from slaifi.domain.assets import AssetId
from slaifi.domain.goals import FinancialGoal
from slaifi.domain.portfolio import Portfolio
from slaifi.engines.goals import evaluate_income_goal, evaluate_return_goal
from slaifi.engines.portfolio import value_portfolio
from slaifi.engines.risk import calculate_risk_statistics


class AnalyzePortfolio:
    """Compose valuation, risk, goal arithmetic, and optional SLAI interpretation."""

    def __init__(self, reasoner: FinancialReasoner | None = None) -> None:
        self._reasoner = reasoner

    def execute(
        self,
        portfolio: Portfolio,
        prices: Mapping[AssetId, Decimal],
        *,
        as_of: datetime,
        initial_cash: Decimal = Decimal("0"),
        returns: Sequence[float] | None = None,
        equity_values: Sequence[float] | None = None,
        periods_per_year: int | None = None,
        risk_free_annual_rate: float = 0.0,
        goal: FinancialGoal | None = None,
        assumed_annual_return_rate: float | None = None,
        assumed_annual_income_yield_rate: float | None = None,
        current_expected_annual_income: Decimal | None = None,
        reasoning_objective: str | None = None,
    ) -> PortfolioAnalysisResult:
        snapshot = value_portfolio(
            portfolio,
            prices,
            as_of=as_of,
            initial_cash=initial_cash,
        )
        risk = None
        if returns is not None or equity_values is not None or periods_per_year is not None:
            if returns is None or equity_values is None or periods_per_year is None:
                raise ValidationError(
                    "returns, equity_values, and periods_per_year must be supplied together"
                )
            weights = [
                valuation.portfolio_weight
                for valuation in snapshot.positions
                if valuation.portfolio_weight is not None
            ]
            risk = calculate_risk_statistics(
                returns,
                equity_values,
                periods_per_year=periods_per_year,
                risk_free_annual_rate=risk_free_annual_rate,
                weights=weights or None,
            )

        goals = None
        if goal is not None:
            income = None
            returns_goal = None
            if goal.income_target is not None:
                income = evaluate_income_goal(
                    goal.income_target,
                    available_capital=max(snapshot.total_value, Decimal("0")),
                    assumed_annual_yield_rate=assumed_annual_income_yield_rate,
                    current_expected_annual_income=current_expected_annual_income,
                )
            if goal.return_target is not None:
                returns_goal = evaluate_return_goal(
                    goal.return_target,
                    assumed_annual_return_rate=assumed_annual_return_rate,
                )
            goals = GoalEvaluationBundle(income=income, returns=returns_goal)

        result = PortfolioAnalysisResult(snapshot=snapshot, risk=risk, goals=goals)
        if self._reasoner is None or not reasoning_objective:
            return result

        reasoning = self._reasoner.reason(
            ReasoningRequest(
                operation="portfolio_analysis",
                evidence=self._evidence(result),
                objective=reasoning_objective,
                constraints=self._goal_constraints(goal),
                assumptions={
                    "periods_per_year": periods_per_year,
                    "risk_free_annual_rate": risk_free_annual_rate,
                    "assumed_annual_return_rate": assumed_annual_return_rate,
                    "assumed_annual_income_yield_rate": assumed_annual_income_yield_rate,
                },
                uncertainty={"prediction_model_used": False, "fx_conversion_used": False},
                correlation_id=portfolio.portfolio_id,
            )
        )
        return PortfolioAnalysisResult(
            snapshot=result.snapshot,
            risk=result.risk,
            goals=result.goals,
            reasoning=reasoning,
        )

    @staticmethod
    def _evidence(result: PortfolioAnalysisResult) -> dict[str, object]:
        snapshot = result.snapshot
        payload: dict[str, object] = {
            "portfolio_id": snapshot.portfolio_id,
            "as_of": snapshot.as_of.isoformat(),
            "base_currency": str(snapshot.base_currency),
            "cash_balance": str(snapshot.cash_balance),
            "securities_market_value": str(snapshot.securities_market_value),
            "total_value": str(snapshot.total_value),
            "positions": [
                {
                    "asset": item.position.asset.display_symbol,
                    "quantity": str(item.position.quantity),
                    "average_cost": str(item.position.average_cost),
                    "market_price": str(item.market_price),
                    "market_value": str(item.market_value),
                    "unrealized_pnl": str(item.unrealized_pnl),
                    "portfolio_weight": item.portfolio_weight,
                }
                for item in snapshot.positions
            ],
        }
        if result.risk is not None:
            payload["risk"] = {
                "observation_count": result.risk.observation_count,
                "annualized_volatility": result.risk.annualized_volatility,
                "annualized_downside_deviation": result.risk.annualized_downside_deviation,
                "maximum_drawdown_rate": result.risk.maximum_drawdown,
                "sharpe_ratio": result.risk.sharpe_ratio,
                "sortino_ratio": result.risk.sortino_ratio,
                "concentration_hhi": result.risk.concentration_hhi,
            }
        if result.goals is not None:
            payload["goal_evaluation"] = {
                "income": result.goals.income,
                "returns": result.goals.returns,
            }
        return payload

    @staticmethod
    def _goal_constraints(goal: FinancialGoal | None) -> dict[str, object]:
        if goal is None:
            return {}
        constraints = goal.constraints
        return {
            "max_drawdown_rate": constraints.max_drawdown_rate,
            "max_position_weight": constraints.max_position_weight,
            "max_sector_weight": constraints.max_sector_weight,
            "max_leverage": constraints.max_leverage,
            "max_short_exposure": constraints.max_short_exposure,
            "allowed_asset_classes": sorted(item.value for item in constraints.allowed_asset_classes),
            "prohibited_asset_classes": sorted(
                item.value for item in constraints.prohibited_asset_classes
            ),
        }
