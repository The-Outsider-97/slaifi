"""SLAI advisor routes: interpret an instruction, then explicitly confirm or reject it."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from slaifi.api import serializers as out
from slaifi.api.dependencies import get_advisor_service
from slaifi.api.schemas.finance import AdvisorConfirm, AdvisorRequest
from slaifi.api.security import MutationGuard
from slaifi.application.advisor import AdvisorService

router = APIRouter(prefix="/api/v1/advisor", tags=["advisor"])
Advisor = Annotated[AdvisorService, Depends(get_advisor_service)]


@router.post("/interpret")
async def interpret(body: AdvisorRequest, advisor: Advisor) -> dict[str, Any]:
    """Parse and preview an instruction. This never changes anything by itself."""

    return out.advisor(
        await advisor.interpret(body.text, portfolio_id=body.portfolio_id, explain=body.explain)
    )


@router.post("/proposals/{proposal_id}/confirm", dependencies=[MutationGuard])
async def confirm(proposal_id: str, body: AdvisorConfirm, advisor: Advisor) -> dict[str, Any]:
    result = await advisor.confirm(
        proposal_id,
        acknowledge_limit_changes=body.acknowledge_limit_changes,
        acknowledge_contradictions=body.acknowledge_contradictions,
    )
    return out.confirm(result)


@router.post("/proposals/{proposal_id}/reject", dependencies=[MutationGuard])
async def reject(proposal_id: str, advisor: Advisor) -> dict[str, Any]:
    advisor.reject(proposal_id)
    return {"rejected": proposal_id}
