"""FastAPI dependency accessors for application services."""

from typing import cast

from fastapi import Request

from slaifi.application.market.get_overview import GetMarketOverview


def get_market_overview_service(request: Request) -> GetMarketOverview:
    """Retrieve the pre-wired use case from application state."""

    service = getattr(request.app.state, "market_overview_service", None)
    if service is None:
        raise RuntimeError("market overview service is not configured")
    return cast(GetMarketOverview, service)
