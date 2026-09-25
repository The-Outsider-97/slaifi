"""SLAIFI backend composition root."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from logs.logger import get_logger

from slaifi import __version__
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
from slaifi.domain.market.models import AssetRef
from slaifi.domain.market.provider import MarketDataProvider
from slaifi.infrastructure.market_data.mock_provider import MockMarketDataProvider
from slaifi.integrations.slai import SlaiFinancialReasoner

logger = get_logger("SLAIFI Composition")


def create_app(
    settings: Settings | None = None,
    market_provider: MarketDataProvider | None = None,
    financial_reasoner: FinancialReasoner | None = None,
    *,
    slai_factory: Any = None,
    slai_shared_memory: Any = None,
) -> FastAPI:
    """Create SLAIFI and wire concrete runtime dependencies at the composition root.

    Logging configuration is deliberately not performed here. The wider SLAI
    host, or ``run_slaifi.py`` when used as the root launcher, owns process-level
    logging configuration.
    """

    runtime_settings = settings or get_settings()
    provider = market_provider or MockMarketDataProvider()
    owns_reasoner = financial_reasoner is None
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

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if owns_reasoner:
                close = getattr(reasoner, "close", None)
                if callable(close):
                    close()

    app = FastAPI(
        title="SLAIFI API",
        version=__version__,
        description="SLAI Financial Intelligence application API",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(runtime_settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )
    install_exception_handlers(app)

    assets = tuple(AssetRef(symbol=symbol) for symbol in runtime_settings.market_overview_symbols)
    app.state.settings = runtime_settings
    app.state.financial_reasoner = reasoner
    app.state.market_overview_service = GetMarketOverview(provider=provider, assets=assets)
    app.state.market_analysis_service = AnalyzeMarketSeries(reasoner=reasoner)
    app.state.portfolio_analysis_service = AnalyzePortfolio(reasoner=reasoner)
    app.state.goal_evaluation_service = EvaluateFinancialGoal(reasoner=reasoner)
    app.include_router(api_router)
    logger.debug("SLAIFI application composition completed")
    return app


app = create_app()
