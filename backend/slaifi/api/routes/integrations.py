"""External-integration status endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from slaifi.api.dependencies import get_financial_reasoner
from slaifi.api.schemas.common import ReasoningResponse
from slaifi.application.contracts import FinancialReasoner

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


@router.get("/slai", response_model=ReasoningResponse)
def slai_status(
    reasoner: Annotated[FinancialReasoner, Depends(get_financial_reasoner)],
) -> ReasoningResponse:
    return ReasoningResponse.from_application(reasoner.status())
