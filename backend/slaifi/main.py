"""SLAIFI backend composition root."""

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from slaifi.api.errors import install_exception_handlers
from slaifi.api.router import api_router
from slaifi.application.analysis import AnalyzeMarketSeries, AnalyzePortfolio
from slaifi.application.contracts import (
    FinancialReasoner,
    ReasoningStatus,
    ReasoningUnavailableError,
)
from slaifi.application.goals import EvaluateFinancialGoal
from slaifi.application.market.get_overview import GetMarketOverview
from slaifi.core.config import Settings, get_settings
from slaifi.core.logging import configure_logging
from slaifi.domain.market.models import AssetRef
from slaifi.domain.market.provider import MarketDataProvider
from slaifi.infrastructure.market_data.mock_provider import MockMarketDataProvider
from slaifi.integrations.slai import SlaiFinancialReasoner


def create_app(
    settings: Settings | None = None,
    market_provider: MarketDataProvider | None = None,
    financial_reasoner: FinancialReasoner | None = None,
    *,
    slai_factory: Any = None,
    slai_shared_memory: Any = None,
) -> FastAPI:
    """Create SLAIFI and wire concrete runtime dependencies at the composition root.

    An embedding SLAI process should inject its existing AgentFactory and
    SharedMemory instances. Standalone SLAIFI can omit them; the SLAI adapter
    then attempts lazy discovery and degrades cleanly when the host is absent.
    """

    runtime_settings = settings or get_settings()
    configure_logging(runtime_settings.log_level)

    app = FastAPI(
        title="SLAIFI API",
        version="0.3.0",
        description="SLAI Financial Intelligence application API",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(runtime_settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )
    install_exception_handlers(app)

    provider = market_provider or MockMarketDataProvider()
    reasoner = financial_reasoner or SlaiFinancialReasoner(
        enabled=runtime_settings.slai_enabled,
        required=runtime_settings.slai_required,
        agent_type=runtime_settings.slai_reasoning_agent,
        reasoning_type=runtime_settings.slai_reasoning_type,
        memory_ttl_seconds=runtime_settings.slai_memory_ttl_seconds,
        factory=slai_factory,
        shared_memory=slai_shared_memory,
    )
    if runtime_settings.slai_required:
        status = reasoner.status()
        if status.status in {ReasoningStatus.UNAVAILABLE, ReasoningStatus.DISABLED}:
            detail = status.warnings[0] if status.warnings else "SLAI runtime unavailable"
            raise ReasoningUnavailableError(detail)

    assets = tuple(
        AssetRef(symbol=symbol)
        for symbol in runtime_settings.market_overview_symbols
    )
    app.state.settings = runtime_settings
    app.state.financial_reasoner = reasoner
    app.state.market_overview_service = GetMarketOverview(provider=provider, assets=assets)
    app.state.market_analysis_service = AnalyzeMarketSeries(reasoner=reasoner)
    app.state.portfolio_analysis_service = AnalyzePortfolio(reasoner=reasoner)
    app.state.goal_evaluation_service = EvaluateFinancialGoal()
    app.include_router(api_router)
    return app


app = create_app()
