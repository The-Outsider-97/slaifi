"""Current portfolio dashboard route."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import ValidationError as PydanticValidationError

from slaifi.api.dependencies import (
    get_market_gateway,
    get_portfolio_analysis_service,
    get_request_id,
    get_runtime_settings,
)
from slaifi.api.schemas.analysis import (
    PortfolioAnalysisResponse,
    PortfolioInput,
    PortfolioPriceBasis,
)
from slaifi.application.analysis import AnalyzePortfolio
from slaifi.core.config import Settings
from slaifi.domain.assets import AssetId
from slaifi.domain.market import MarketGateway

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])


@router.get(
    "/current",
    response_model=PortfolioAnalysisResponse,
    responses={204: {"description": "No portfolio source configured"}},
)
async def current_portfolio(
    settings: Annotated[Settings, Depends(get_runtime_settings)],
    gateway: Annotated[MarketGateway, Depends(get_market_gateway)],
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
    assets: list[AssetId] = []
    seen: set[AssetId] = set()
    for trade in portfolio.trades:
        if trade.asset not in seen:
            seen.add(trade.asset)
            assets.append(trade.asset)

    prices: dict[AssetId, Decimal] = {}
    basis = PortfolioPriceBasis(mode="none")
    if assets:
        fetched = await gateway.fetch_quotes(tuple(assets))
        quotes = [f.quote for f in fetched if f.quote is not None]
        prices = {quote.asset: quote.price for quote in quotes}
        missing = [asset.display_symbol for asset in assets if asset not in prices]
        if missing:
            raise HTTPException(
                status_code=503,
                detail=f"NOT AVAILABLE: no live or saved price for {', '.join(missing)}",
            )
        stale = [q for q in quotes if q.last_known]
        basis = PortfolioPriceBasis(
            mode="last_known" if stale else "live",
            sources=sorted({q.source for q in quotes}),
            last_known_symbols=[q.asset.display_symbol for q in stale],
            oldest_observed_at=min(q.observed_at for q in quotes),
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
    response = PortfolioAnalysisResponse.from_application(result)
    response.price_basis = basis
    return response
