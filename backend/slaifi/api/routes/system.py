"""Storage, audit and reconciliation status."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from slaifi.api import serializers as out
from slaifi.api.dependencies import get_finance_store, get_paper_service, get_runtime_settings
from slaifi.api.security import MutationGuard
from slaifi.application.contracts import FinanceStore
from slaifi.application.paper import PaperTradingService
from slaifi.core.config import Settings

router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/status")
async def status(
    request: Request,
    store: Annotated[FinanceStore, Depends(get_finance_store)],
    settings: Annotated[Settings, Depends(get_runtime_settings)],
) -> dict[str, Any]:
    chain_ok, chain_detail = store.verify_audit_chain()
    return {
        "storage_status": getattr(request.app.state, "storage_status", "unknown"),
        "audit_chain_intact": chain_ok,
        "audit_chain_detail": chain_detail,
        "market_provider": settings.market_provider,
        "data_mode": getattr(request.app.state, "data_mode", "unknown"),
        "real_money_trading": "unavailable",
        "paper_trading": {
            "allow_illustrative_execution": settings.paper_allow_illustrative_execution,
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
