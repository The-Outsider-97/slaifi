"""Top-level API router composition."""

from fastapi import APIRouter

from slaifi.api.routes.analysis import router as analysis_router
from slaifi.api.routes.goals import router as goals_router
from slaifi.api.routes.health import router as health_router
from slaifi.api.routes.integrations import router as integrations_router
from slaifi.api.routes.market import router as market_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(market_router)
api_router.include_router(analysis_router)
api_router.include_router(goals_router)
api_router.include_router(integrations_router)
