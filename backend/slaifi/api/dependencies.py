"""FastAPI dependency accessors for pre-wired application services."""

from typing import Annotated, cast

from fastapi import Header, Request

from slaifi.application.analysis import AnalyzeMarketSeries, AnalyzePortfolio
from slaifi.application.contracts import FinancialReasoner
from slaifi.application.goals import EvaluateFinancialGoal
from slaifi.application.market import GetMarketHistory
from slaifi.application.market.get_overview import GetMarketOverview
from slaifi.core.config import Settings
from slaifi.core.utils.errors import ValidationError
from slaifi.domain.market import MarketGateway


def _state_value(request: Request, name: str) -> object:
    value = getattr(request.app.state, name, None)
    if value is None:
        raise RuntimeError(f"application dependency {name!r} is not configured")
    return value


def get_market_overview_service(request: Request) -> GetMarketOverview:
    return cast(GetMarketOverview, _state_value(request, "market_overview_service"))


def get_market_analysis_service(request: Request) -> AnalyzeMarketSeries:
    return cast(AnalyzeMarketSeries, _state_value(request, "market_analysis_service"))


def get_market_history_service(request: Request) -> GetMarketHistory:
    return cast(GetMarketHistory, _state_value(request, "market_history_service"))


def get_market_gateway(request: Request) -> MarketGateway:
    return cast(MarketGateway, _state_value(request, "market_data_provider"))


def get_portfolio_analysis_service(request: Request) -> AnalyzePortfolio:
    return cast(AnalyzePortfolio, _state_value(request, "portfolio_analysis_service"))


def get_goal_evaluation_service(request: Request) -> EvaluateFinancialGoal:
    return cast(EvaluateFinancialGoal, _state_value(request, "goal_evaluation_service"))


def get_financial_reasoner(request: Request) -> FinancialReasoner:
    return cast(FinancialReasoner, _state_value(request, "financial_reasoner"))


def get_runtime_settings(request: Request) -> Settings:
    return cast(Settings, _state_value(request, "settings"))


def get_request_id(
    x_request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
) -> str | None:
    """Validate caller trace metadata without using it as SLAI's unique correlation key."""
    if x_request_id is None:
        return None
    normalized = x_request_id.strip()
    if not normalized:
        raise ValidationError("X-Request-ID must not be blank")
    if len(normalized) > 128:
        raise ValidationError("X-Request-ID must not exceed 128 characters")
    return normalized


# ---------------------------------------------------------------------------------------------
# Finance services (paper trading, strategies, goals, recommendations, advisor)
from slaifi.application.advisor import AdvisorService  # noqa: E402
from slaifi.application.contracts import FinanceStore  # noqa: E402
from slaifi.application.goals import GoalTracker  # noqa: E402
from slaifi.application.market import MarketDataService  # noqa: E402
from slaifi.application.paper import PaperTradingService  # noqa: E402
from slaifi.application.portfolio import PortfolioGuidanceService  # noqa: E402
from slaifi.application.recommendations import RecommendationService  # noqa: E402
from slaifi.application.strategies import StrategyService  # noqa: E402


def get_finance_store(request: Request) -> FinanceStore:
    return cast(FinanceStore, _state_value(request, "finance_store"))


def get_market_data_service(request: Request) -> MarketDataService:
    return cast(MarketDataService, _state_value(request, "market_data_service"))


def get_strategy_service(request: Request) -> StrategyService:
    return cast(StrategyService, _state_value(request, "strategy_service"))


def get_paper_service(request: Request) -> PaperTradingService:
    return cast(PaperTradingService, _state_value(request, "paper_service"))


def get_goal_tracker(request: Request) -> GoalTracker:
    return cast(GoalTracker, _state_value(request, "goal_tracker"))


def get_recommendation_service(request: Request) -> RecommendationService:
    return cast(RecommendationService, _state_value(request, "recommendation_service"))


def get_guidance_service(request: Request) -> PortfolioGuidanceService:
    return cast(PortfolioGuidanceService, _state_value(request, "guidance_service"))


def get_advisor_service(request: Request) -> AdvisorService:
    return cast(AdvisorService, _state_value(request, "advisor_service"))
