"""FastAPI dependency accessors for pre-wired application services."""

from typing import Annotated, cast

from fastapi import Header, Request

from slaifi.application.analysis import AnalyzeMarketSeries, AnalyzePortfolio
from slaifi.application.contracts import FinancialReasoner
from slaifi.application.goals import EvaluateFinancialGoal
from slaifi.application.market.get_overview import GetMarketOverview
from slaifi.core.config import Settings
from slaifi.core.utils.errors import ValidationError


def _state_value(request: Request, name: str) -> object:
    value = getattr(request.app.state, name, None)
    if value is None:
        raise RuntimeError(f"application dependency {name!r} is not configured")
    return value


def get_market_overview_service(request: Request) -> GetMarketOverview:
    return cast(GetMarketOverview, _state_value(request, "market_overview_service"))


def get_market_analysis_service(request: Request) -> AnalyzeMarketSeries:
    return cast(AnalyzeMarketSeries, _state_value(request, "market_analysis_service"))


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
