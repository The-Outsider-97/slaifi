"""Current portfolio dashboard route."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import ValidationError as PydanticValidationError

from slaifi.api.dependencies import (
    get_market_data_provider,
    get_portfolio_analysis_service,
    get_request_id,
    get_runtime_settings,
)
from slaifi.api.schemas.analysis import PortfolioAnalysisResponse, PortfolioInput
from slaifi.application.analysis import AnalyzePortfolio
from slaifi.core.config import Settings
from slaifi.core.utils.errors import ConfigurationError, InfrastructureError
from slaifi.domain.assets import AssetId
from slaifi.domain.market.provider import MarketDataProvider

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])


@router.get(
    "/current",
    response_model=PortfolioAnalysisResponse,
    responses={204: {"description": "No portfolio source configured"}},
)
async def current_portfolio(
    settings: Annotated[Settings, Depends(get_runtime_settings)],
    provider: Annotated[MarketDataProvider, Depends(get_market_data_provider)],
    service: Annotated[AnalyzePortfolio, Depends(get_portfolio_analysis_service)],
    request_id: Annotated[str | None, Depends(get_request_id)],
    include_reasoning: Annotated[
        bool,
        Query(
            description=(
                "Run the optional SLAI interpretation pipeline. False keeps the normal "
                "portfolio dashboard deterministic and avoids unnecessary agent latency."
            )
        ),
    ] = False,
) -> PortfolioAnalysisResponse | Response:
    """Return the current portfolio valued with authoritative provider prices."""

    path = settings.portfolio_file
    if path is None or not path.exists():
        return Response(status_code=204)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise InfrastructureError(
            "Configured portfolio source could not be read",
            component="portfolio_store",
            operation="read",
            cause=exc,
            retryable=True,
        ) from exc
    except json.JSONDecodeError as exc:
        raise ConfigurationError(
            "Configured portfolio source is not valid JSON",
            component="portfolio_store",
            operation="decode",
            cause=exc,
        ) from exc

    try:
        portfolio_input = PortfolioInput.model_validate(payload)
    except PydanticValidationError as exc:
        raise ConfigurationError(
            "Configured portfolio source does not match the SLAIFI portfolio schema",
            component="portfolio_store",
            operation="validate",
            cause=exc,
        ) from exc

    portfolio = portfolio_input.to_domain()
    assets = service.required_price_assets(portfolio)

    prices: dict[AssetId, Decimal] = {}
    if assets:
        quotes = await provider.get_quotes(assets)
        prices = {quote.asset: quote.price for quote in quotes}
        missing = [asset.display_symbol for asset in assets if asset not in prices]
        if missing:
            raise InfrastructureError(
                "Current market prices are unavailable for one or more open positions",
                component="market_data",
                operation="portfolio_quotes",
                context={"missing_symbols": missing},
                retryable=True,
            )

    result = service.execute(
        portfolio,
        prices,
        as_of=datetime.now(UTC),
        reasoning_objective=(
            "Explain the current portfolio structure, concentration, material exposures, "
            "risk considerations, uncertainty, and relevant goal constraints using only "
            "the supplied authoritative portfolio evidence. Explicitly state missing "
            "evidence and do not invent prices, holdings, performance, or recommendations."
            if include_reasoning
            else None
        ),
        request_id=request_id,
    )
    return PortfolioAnalysisResponse.from_application(result)
