"""SLAIFI backend composition root."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import inspect
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from logs.logger import get_logger

from slaifi import __version__
from slaifi.api.errors import install_exception_handlers
from slaifi.api.router import api_router
from slaifi.application.analysis import (
    AnalyzeMarketSeries,
    AnalyzePortfolio,
)
from slaifi.application.contracts import (
    FinancialReasoner,
    ReasoningStatus,
    ReasoningUnavailableError,
)
from slaifi.application.goals import (
    EvaluateFinancialGoal,
)
from slaifi.application.market import (
    GetMarketHistory,
    GetMarketOverview,
)
from slaifi.core.config import Settings, get_settings
from slaifi.domain.market.models import AssetRef
from slaifi.domain.market.provider import (
    MarketDataProvider,
)
from slaifi.infrastructure.market_data import (
    MockMarketDataProvider,
    TwelveDataMarketDataProvider,
)
from slaifi.integrations.slai import (
    SlaiFinancialReasoner,
)

logger = get_logger("SLAIFI Composition")


def _build_market_provider(
    settings: Settings,
) -> MarketDataProvider:
    if settings.market_provider == "mock":
        if settings.environment == "production":
            raise RuntimeError(
                "SLAIFI refuses to start in production "
                "with the mock market provider"
            )

        return MockMarketDataProvider()

    if settings.market_provider == "twelvedata":
        if not settings.market_api_key:
            raise RuntimeError(
                "SLAIFI_MARKET_API_KEY is required when "
                "SLAIFI_MARKET_PROVIDER=twelvedata"
            )

        return TwelveDataMarketDataProvider(
            api_key=settings.market_api_key,
            timeout_seconds=(
                settings.market_http_timeout_seconds
            ),
        )

    raise RuntimeError(
        "Unsupported SLAIFI market provider: "
        f"{settings.market_provider}"
    )


def create_app(
    settings: Settings | None = None,
    market_provider: MarketDataProvider | None = None,
    financial_reasoner: FinancialReasoner | None = None,
    *,
    slai_factory: Any = None,
    slai_shared_memory: Any = None,
) -> FastAPI:
    """Create and wire the SLAIFI application."""

    runtime_settings = settings or get_settings()

    owns_provider = market_provider is None
    provider = (
        market_provider
        if market_provider is not None
        else _build_market_provider(runtime_settings)
    )

    owns_reasoner = financial_reasoner is None

    reasoner = (
        financial_reasoner
        or SlaiFinancialReasoner(
            enabled=runtime_settings.slai_enabled,
            required=runtime_settings.slai_required,
            agent_type=(
                runtime_settings.slai_reasoning_agent
            ),
            reasoning_type=(
                runtime_settings.slai_reasoning_type
            ),
            memory_ttl_seconds=(
                runtime_settings.slai_memory_ttl_seconds
            ),
            factory=slai_factory,
            shared_memory=slai_shared_memory,
        )
    )

    if runtime_settings.slai_required:
        status = reasoner.status()

        if status.status in {
            ReasoningStatus.UNAVAILABLE,
            ReasoningStatus.DISABLED,
        }:
            detail = (
                status.warnings[0]
                if status.warnings
                else "SLAI runtime unavailable"
            )
            raise ReasoningUnavailableError(
                detail
            )

    @asynccontextmanager
    async def lifespan(
        _: FastAPI,
    ) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if owns_reasoner:
                close_reasoner = getattr(
                    reasoner,
                    "close",
                    None,
                )

                if callable(close_reasoner):
                    result = close_reasoner()
                    if inspect.isawaitable(result):
                        await result

            if owns_provider:
                close_provider = getattr(
                    provider,
                    "close",
                    None,
                )

                if callable(close_provider):
                    result = close_provider()
                    if inspect.isawaitable(result):
                        await result

    app = FastAPI(
        title="SLAIFI API",
        version=__version__,
        description=(
            "SLAI Financial Intelligence application API"
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(
            runtime_settings.cors_origins
        ),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=[
            "Content-Type",
            "X-Request-ID",
        ],
    )

    install_exception_handlers(app)

    assets = tuple(
        AssetRef(symbol=symbol)
        for symbol
        in runtime_settings.market_overview_symbols
    )

    app.state.settings = runtime_settings
    app.state.financial_reasoner = reasoner
    app.state.market_data_provider = provider

    app.state.market_overview_service = (
        GetMarketOverview(
            provider=provider,
            assets=assets,
        )
    )

    app.state.market_history_service = (
        GetMarketHistory(
            provider=provider,
        )
    )

    app.state.market_analysis_service = (
        AnalyzeMarketSeries(
            reasoner=reasoner,
        )
    )

    app.state.portfolio_analysis_service = (
        AnalyzePortfolio(
            reasoner=reasoner,
        )
    )

    app.state.goal_evaluation_service = (
        EvaluateFinancialGoal(
            reasoner=reasoner,
        )
    )

    app.include_router(api_router)

    logger.debug(
        "SLAIFI application composition completed"
    )

    return app


app = create_app()
