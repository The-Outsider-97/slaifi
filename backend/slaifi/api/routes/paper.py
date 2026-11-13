"""Paper-trading routes. Everything here is simulated; no route can move real money."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from slaifi.api import serializers as out
from slaifi.api.dependencies import get_guidance_service, get_paper_service
from slaifi.api.schemas.finance import (
    CashRequest,
    CreatePortfolio,
    OrderRequestBody,
    PlatformFeesBody,
    PortfolioStrategy,
    ResetRequest,
)
from slaifi.api.security import MutationGuard
from slaifi.application.paper import PaperTradingService
from slaifi.application.portfolio import PortfolioGuidanceService
from slaifi.core.utils.errors import ValidationError
from slaifi.domain.assets import AssetClass
from slaifi.domain.portfolio import TradeSide

router = APIRouter(prefix="/api/v1/paper", tags=["paper-trading"])
Paper = Annotated[PaperTradingService, Depends(get_paper_service)]


@router.get("/fees")
async def get_fees(paper: Paper) -> dict[str, Any]:
    """What the trading platform charges per trade and per withdrawal (editable in Settings)."""

    return {**out.platform_fees(paper.platform_fees()), "simulated": True}


@router.put("/fees", dependencies=[MutationGuard])
async def set_fees(body: PlatformFeesBody, paper: Paper) -> dict[str, Any]:
    if body.per_trade is None and body.per_withdrawal is None:
        raise ValidationError("send per_trade, per_withdrawal or both")
    fees = paper.set_platform_fees(per_trade=body.per_trade, per_withdrawal=body.per_withdrawal)
    return {**out.platform_fees(fees), "simulated": True}


@router.get("/portfolios")
async def list_portfolios(paper: Paper) -> dict[str, Any]:
    return {
        "portfolios": [out.portfolio_meta(p) for p in paper.list_portfolios()],
        "simulated": True,
    }


@router.post("/portfolios", dependencies=[MutationGuard], status_code=201)
async def create_portfolio(body: CreatePortfolio, paper: Paper) -> dict[str, Any]:
    view = await paper.create_portfolio(
        name=body.name,
        starting_capital=body.starting_capital,
        currency=body.currency,
        strategy_id=body.strategy_id,
    )
    return out.portfolio_view(view)


@router.get("/portfolios/{portfolio_id}")
async def get_portfolio(portfolio_id: str, paper: Paper) -> dict[str, Any]:
    return out.portfolio_view(await paper.view(portfolio_id))


@router.put("/portfolios/{portfolio_id}/strategy", dependencies=[MutationGuard])
async def set_strategy(portfolio_id: str, body: PortfolioStrategy, paper: Paper) -> dict[str, Any]:
    return out.portfolio_meta(paper.set_strategy(portfolio_id, body.strategy_id))


@router.post("/portfolios/{portfolio_id}/deposit", dependencies=[MutationGuard])
async def deposit(portfolio_id: str, body: CashRequest, paper: Paper) -> dict[str, Any]:
    return out.portfolio_view(await paper.deposit(portfolio_id, body.amount, note=body.note))


@router.post("/portfolios/{portfolio_id}/withdraw", dependencies=[MutationGuard])
async def withdraw(portfolio_id: str, body: CashRequest, paper: Paper) -> dict[str, Any]:
    return out.portfolio_view(await paper.withdraw(portfolio_id, body.amount, note=body.note))


def _order_args(body: OrderRequestBody) -> dict[str, Any]:
    try:
        asset_class = AssetClass(body.asset_class) if body.asset_class else None
    except ValueError as exc:
        raise ValidationError("unknown asset_class") from exc
    if not body.close_position and (body.quantity is None) == (body.notional is None):
        raise ValidationError("provide exactly one of quantity or notional (or close_position)")
    return {
        "symbol": body.symbol,
        "side": TradeSide(body.side),
        "quantity": body.quantity,
        "notional": body.notional,
        "close_position": body.close_position,
        "client_order_id": body.client_order_id,
        "exchange": body.exchange,
        "asset_class": asset_class,
    }


@router.post("/portfolios/{portfolio_id}/orders/preview")
async def preview_order(portfolio_id: str, body: OrderRequestBody, paper: Paper) -> dict[str, Any]:
    """Price and validate an order without recording it. Read-only, so no client header."""

    return out.order_outcome(
        await paper.place_order(portfolio_id, dry_run=True, **_order_args(body))
    )


@router.post("/portfolios/{portfolio_id}/orders", dependencies=[MutationGuard])
async def place_order(portfolio_id: str, body: OrderRequestBody, paper: Paper) -> dict[str, Any]:
    return out.order_outcome(await paper.place_order(portfolio_id, **_order_args(body)))


@router.get("/portfolios/{portfolio_id}/history")
async def history(
    portfolio_id: str, paper: Paper, limit: int = Query(200, ge=1, le=1000)
) -> dict[str, Any]:
    return {"entries": [out.history_entry(h) for h in paper.history(portfolio_id, limit)]}


@router.get("/portfolios/{portfolio_id}/performance")
async def performance(portfolio_id: str, paper: Paper) -> dict[str, Any]:
    return out.performance(await paper.performance(portfolio_id))


@router.post("/portfolios/{portfolio_id}/reset", dependencies=[MutationGuard])
async def reset(portfolio_id: str, body: ResetRequest, paper: Paper) -> dict[str, Any]:
    return out.portfolio_view(
        await paper.reset(
            portfolio_id, confirm=body.confirm, starting_capital=body.starting_capital
        )
    )


@router.get("/portfolios/{portfolio_id}/reconcile")
async def reconcile(portfolio_id: str, paper: Paper) -> dict[str, Any]:
    return out.reconciliation(paper.reconcile(portfolio_id))


@router.get("/portfolios/{portfolio_id}/guidance")
async def guidance(
    portfolio_id: str,
    svc: Annotated[PortfolioGuidanceService, Depends(get_guidance_service)],
    strategy_id: str | None = None,
    explain: bool = False,
) -> dict[str, Any]:
    return out.guidance(await svc.guidance(portfolio_id, strategy_id=strategy_id, explain=explain))
