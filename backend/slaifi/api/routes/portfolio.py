"""Current portfolio dashboard route."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
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
from slaifi.domain.assets import AssetId
from slaifi.domain.market.provider import MarketDataProvider
from slaifi.engines.portfolio import build_positions

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
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500,
            detail="Configured portfolio source could not be read",
        ) from exc

    try:
        portfolio_input = PortfolioInput.model_validate(payload)
    except PydanticValidationError as exc:
        raise HTTPException(
            status_code=500,
            detail="Configured portfolio source does not match the SLAIFI portfolio schema",
        ) from exc

    portfolio = portfolio_input.to_domain()
    open_positions = build_positions(portfolio.trades)
    assets: tuple[AssetId, ...] = tuple(
        position.asset for position in open_positions if position.quantity > 0
    )

    prices: dict[AssetId, Decimal] = {}
    if assets:
        quotes = await provider.get_quotes(assets)
        prices = {quote.asset: quote.price for quote in quotes}
        missing = [asset.display_symbol for asset in assets if asset not in prices]
        if missing:
            raise HTTPException(
                status_code=503,
                detail=f"Current market prices unavailable for: {', '.join(missing)}",
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
