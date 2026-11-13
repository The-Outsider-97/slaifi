"""Optional SLAI agents: switches, Knowledge look-ups and allocation suggestions."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from slaifi.api import serializers as out
from slaifi.api.dependencies import (
    get_agent_switches,
    get_allocation_service,
    get_knowledge_library,
    get_learning_sharing,
)
from slaifi.api.schemas.finance import AgentSwitch, ApplyAllocation
from slaifi.api.security import MutationGuard
from slaifi.application.agents import AgentSwitches
from slaifi.application.allocation import AllocationService
from slaifi.application.allocation.service import FOCUSES
from slaifi.application.contracts import AgentName, KnowledgeLibrary
from slaifi.application.learning import LearningSharing

router = APIRouter(prefix="/api/v1", tags=["agents"])
Switches = Annotated[AgentSwitches, Depends(get_agent_switches)]
Library = Annotated[KnowledgeLibrary, Depends(get_knowledge_library)]
Allocation = Annotated[AllocationService, Depends(get_allocation_service)]
Sharing = Annotated[LearningSharing, Depends(get_learning_sharing)]


def _known(name: str) -> AgentName:
    try:
        return AgentName(name)
    except ValueError:
        raise HTTPException(404, f"There is no optional agent called {name!r}.") from None


@router.get("/system/agents")
async def agents(switches: Switches) -> dict[str, Any]:
    """Each optional SLAI agent, whether it is switched on, and how its last use went."""

    return {
        "agents": [out.agent_status(s) for s in switches.all_statuses()],
        "note": "Optional agents are off until you switch them on. They only advise or keep records; "
        "SLAIFI re-checks everything against your strategy and never acts on an agent's output by itself.",
    }


@router.put("/system/agents/{name}", dependencies=[MutationGuard])
async def switch_agent(name: str, body: AgentSwitch, switches: Switches) -> dict[str, Any]:
    return out.agent_status(switches.set_enabled(_known(name), body.enabled))


@router.post("/system/agents/{name}/check", dependencies=[MutationGuard])
async def check_agent(name: str, request: Request, switches: Switches) -> dict[str, Any]:
    """Start the agent now (instead of at first use) so Settings can say whether it works."""

    agent = _known(name)
    if switches.is_enabled(agent):
        check = request.app.state.agent_checks.get(agent)
        if check is not None:
            await asyncio.to_thread(check)
    return out.agent_status(switches.status(agent))


@router.get("/knowledge/search")
async def knowledge_search(
    library: Library,
    q: Annotated[str, Query(min_length=2, max_length=300)],
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> dict[str, Any]:
    """Passages from SLAIFI's own guides (needs the Knowledge agent switched on)."""

    return out.knowledge_answer(library.search(q, limit))


@router.get("/paper/portfolios/{portfolio_id}/allocation")
async def allocation(
    portfolio_id: str,
    svc: Allocation,
    symbols: Annotated[str | None, Query(max_length=300)] = None,
    watchlist: bool = False,
    focus: str = "steadiest",
) -> dict[str, Any]:
    """A steadier mix of the portfolio's holdings (and optional extras) within the strategy's limits.

    Needs the Financial agent switched on. Advice only; nothing is ordered until you apply it.
    """

    if focus not in FOCUSES:
        raise HTTPException(422, f"focus must be one of {', '.join(FOCUSES)}")
    extra = tuple(s.strip() for s in (symbols or "").split(",") if s.strip())[:20]
    return out.allocation(
        await svc.suggest(portfolio_id, symbols=extra, include_watchlist=watchlist, focus=focus)
    )


@router.post("/paper/portfolios/{portfolio_id}/allocation/apply", dependencies=[MutationGuard])
async def apply_allocation(
    portfolio_id: str, body: ApplyAllocation, svc: Allocation
) -> dict[str, Any]:
    """Place the paper orders of a suggestion: all of them, or just ``symbols``.

    The amounts come from the suggestion kept on the server, never from this request. Every order
    goes through the normal paper-trading checks and platform fees; refused orders are reported.
    """

    symbols = tuple(s.strip() for s in body.symbols or () if s.strip()) or None
    return out.applied_allocation(await svc.apply(portfolio_id, body.suggestion_id, symbols))


@router.get("/learning/slai-memory")
async def slai_memory(sharing: Sharing) -> dict[str, Any]:
    """What SLAI's Learning agent has recorded from SLAIFI (needs the Learning agent switched on)."""

    return out.learning_recall(await asyncio.to_thread(sharing.recall))


@router.post("/learning/slai-memory/share", dependencies=[MutationGuard])
async def share_with_slai(sharing: Sharing) -> dict[str, Any]:
    """Send the recommendation outcomes SLAIFI has measured to SLAI's Learning agent.

    Sending is safe to repeat: outcomes SLAI already holds are reported as duplicates.
    """

    return out.learning_share(await asyncio.to_thread(sharing.share))
