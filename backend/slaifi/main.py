"""SLAIFI backend composition root."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from slaifi.api.router import api_router
from slaifi.application.market.get_overview import GetMarketOverview
from slaifi.core.config.settings import Settings, get_settings
from slaifi.core.logging.setup import configure_logging
from slaifi.domain.market.models import AssetRef
from slaifi.domain.market.provider import MarketDataProvider
from slaifi.infrastructure.market_data.mock_provider import MockMarketDataProvider


def create_app(
    settings: Settings | None = None,
    market_provider: MarketDataProvider | None = None,
) -> FastAPI:
    """Create the FastAPI application and wire concrete adapters to use cases."""

    runtime_settings = settings or get_settings()
    configure_logging(runtime_settings.log_level)

    app = FastAPI(
        title="SLAIFI API",
        version="0.1.0",
        description="SLAI Financial Intelligence application API",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Content-Type"],
    )

    provider = market_provider or MockMarketDataProvider()
    assets = tuple(AssetRef(symbol=symbol) for symbol in runtime_settings.market_overview_symbols)
    app.state.market_overview_service = GetMarketOverview(provider=provider, assets=assets)
    app.include_router(api_router)
    return app


app = create_app()
