"""Storage, audit and reconciliation status."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from slaifi.api import serializers as out
from slaifi.api.dependencies import (
    get_finance_store,
    get_market_data_service,
    get_paper_service,
    get_runtime_settings,
)
from slaifi.api.security import MutationGuard
from slaifi.application.contracts import FinanceStore
from slaifi.application.market import MarketDataService
from slaifi.application.paper import PaperTradingService
from slaifi.core.config import Settings

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/status")
async def status(
    request: Request,
    store: Annotated[FinanceStore, Depends(get_finance_store)],
    settings: Annotated[Settings, Depends(get_runtime_settings)],
    market: Annotated[MarketDataService, Depends(get_market_data_service)],
) -> dict[str, Any]:
    chain_ok, chain_detail = store.verify_audit_chain()
    return {
        "storage_status": getattr(request.app.state, "storage_status", "unknown"),
        "audit_chain_intact": chain_ok,
        "audit_chain_detail": chain_detail,
        "market_providers": [
            {"name": p.name, "configured": p.configured, "state": p.state}
            for p in market.provider_status()
        ],
        "market_configured": market.configured,
        "data_mode": market.data_mode,
        "real_money_trading": "unavailable",
        "paper_trading": {
            "allow_closed_market_execution": settings.paper_allow_closed_market_execution,
            "max_quote_age_seconds": settings.paper_max_quote_age_seconds,
        },
        "slai_enabled": settings.slai_enabled,
        "client_header_required": settings.api_require_client_header,
    }


@router.get("/audit")
async def audit(
    store: Annotated[FinanceStore, Depends(get_finance_store)],
    limit: int = Query(100, ge=1, le=1000),
    subject: str | None = None,
) -> dict[str, Any]:
    return {"entries": [out.audit_entry(a) for a in store.list_audit(limit, subject)]}


@router.get("/reconcile")
async def reconcile(
    paper: Annotated[PaperTradingService, Depends(get_paper_service)],
) -> dict[str, Any]:
    return out.reconciliation(paper.reconcile(None))


@router.post("/backup", dependencies=[MutationGuard])
async def backup(store: Annotated[FinanceStore, Depends(get_finance_store)]) -> dict[str, Any]:
    return {"backup": store.backup("manual")}


@router.get("/providers")
async def providers(
    market: Annotated[MarketDataService, Depends(get_market_data_service)],
) -> dict[str, Any]:
    """Which market-data sources are configured and how each is doing (never includes keys)."""

    return {
        "configured": market.configured,
        "providers": [out.provider_status(p) for p in market.provider_status()],
    }


@router.post("/providers/check", dependencies=[MutationGuard])
async def check_providers(
    market: Annotated[MarketDataService, Depends(get_market_data_service)],
) -> dict[str, Any]:
    """Make one real request per configured provider and report what happened."""

    return {"checks": [out.provider_check(c) for c in await market.check_providers()]}
