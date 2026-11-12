"""SLAIFI backend composition root."""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from logs.logger import get_logger

from slaifi import __version__
from slaifi.api.errors import install_exception_handlers
from slaifi.api.local_access import LocalAccessMiddleware
from slaifi.api.router import api_router
from slaifi.api.static_ui import mount_frontend
from slaifi.application.advisor import AdvisorService
from slaifi.application.analysis import AnalyzeMarketSeries, AnalyzePortfolio
from slaifi.application.contracts import (
    FinanceStore,
    FinancialReasoner,
    NullSafetyReviewer,
    ReasoningStatus,
    ReasoningUnavailableError,
    SafetyReviewer,
)
from slaifi.application.goals import EvaluateFinancialGoal, GoalTracker
from slaifi.application.market import GetMarketHistory, GetMarketOverview, MarketDataService
from slaifi.application.paper import PaperTradingService
from slaifi.application.portfolio import PortfolioGuidanceService
from slaifi.application.recommendations import RecommendationService
from slaifi.application.strategies import StrategyService
from slaifi.core.config import Settings, get_settings
from slaifi.domain.market import MarketCache, MarketGateway
from slaifi.domain.market.models import AssetRef
from slaifi.domain.paper import ExecutionPolicy
from slaifi.infrastructure.market_data import InMemoryMarketCache, build_gateway
from slaifi.infrastructure.persistence import SqliteFinanceStore
from slaifi.integrations.slai import SlaiFinancialReasoner, SlaiSafetyReviewer

logger = get_logger("SLAIFI Composition")


def _resolve_data_dir(settings: Settings) -> Path:
    """Use the explicit setting, else SLAI's own per-application data folder (reused, not re-invented)."""

    if settings.data_dir is not None:
        return Path(settings.data_dir)
    from applications.tools.storage import default_data_dir

    return Path(str(default_data_dir("slaifi", "SLAIFI")))


def _open_market_cache(settings: Settings) -> MarketCache:
    """Durable last-known cache next to the ledger; falls back to memory if it cannot be opened."""

    try:
        from slaifi.infrastructure.market_data.sqlite_cache import SqliteMarketCache

        data_dir = _resolve_data_dir(settings)
        data_dir.mkdir(parents=True, exist_ok=True)
        return SqliteMarketCache(data_dir / "market_cache.db")
    except Exception as exc:  # noqa: BLE001 - live data still works without a durable cache
        logger.warning("Last-known market cache is in memory only (%s)", type(exc).__name__)
        return InMemoryMarketCache()


def _open_store(settings: Settings) -> tuple[FinanceStore, str]:
    """Open the authoritative ledger and verify it. Returns the store and a storage status.

    The status is ``ok`` only when SQLite's integrity check passes and the audit hash chain is
    intact; anything else disables order placement (reads keep working) until restored.
    """

    data_dir = _resolve_data_dir(settings)
    data_dir.mkdir(parents=True, exist_ok=True)
    store = SqliteFinanceStore(data_dir / "slaifi.db", backups_dir=data_dir / "backups")
    status = "ok"
    try:
        integrity = store.integrity()
        if integrity.lower() != "ok":
            status = f"integrity check failed: {integrity}"
        else:
            chain_ok, detail = store.verify_audit_chain()
            if not chain_ok:
                status = f"audit chain broken: {detail}"
    except Exception as exc:  # noqa: BLE001
        status = f"storage check failed: {type(exc).__name__}"
    if status == "ok":
        try:
            store.backup("startup")
        except Exception as exc:  # noqa: BLE001 - a failed backup must not stop the application
            logger.warning("Startup backup failed: %s", exc)
    else:
        logger.error("Ledger is not trustworthy, order placement is disabled: %s", status)
    return store, status


def create_app(
    settings: Settings | None = None,
    market_gateway: MarketGateway | None = None,
    financial_reasoner: FinancialReasoner | None = None,
    *,
    slai_factory: Any = None,
    slai_shared_memory: Any = None,
    finance_store: FinanceStore | None = None,
    safety_reviewer: SafetyReviewer | None = None,
    access_token: str | None = None,
    security_headers: Mapping[str, str] | None = None,
) -> FastAPI:
    """Create and wire the SLAIFI application without coupling the financial core to SLAI.

    ``access_token`` (set by the launcher) switches on the local-access rules every SLAI application
    follows: token-to-cookie handshake, Host/Origin checks and ``security_headers`` on responses.
    Tests and ``uvicorn slaifi.main:app`` leave it unset.
    """

    runtime_settings = settings or get_settings()
    owns_gateway = market_gateway is None
    market_cache: MarketCache | None = None
    if market_gateway is None:
        market_cache = _open_market_cache(runtime_settings)
        gateway: MarketGateway = build_gateway(runtime_settings, cache=market_cache)
    else:
        gateway = market_gateway

    owns_reasoner = financial_reasoner is None
    reasoner = financial_reasoner or SlaiFinancialReasoner(
        enabled=runtime_settings.slai_enabled,
        required=runtime_settings.slai_required,
        agent_type=runtime_settings.slai_reasoning_agent,
        reasoning_type=runtime_settings.slai_reasoning_type,
        quality_enabled=runtime_settings.slai_quality_enabled,
        quality_agent_type=runtime_settings.slai_quality_agent,
        refinement_enabled=runtime_settings.slai_quality_refinement_enabled,
        memory_ttl_seconds=runtime_settings.slai_memory_ttl_seconds,
        factory=slai_factory,
        shared_memory=slai_shared_memory,
    )

    if runtime_settings.slai_required:
        status = reasoner.status()
        if status.status in {ReasoningStatus.UNAVAILABLE, ReasoningStatus.DISABLED}:
            detail = status.warnings[0] if status.warnings else "SLAI runtime unavailable"
            raise ReasoningUnavailableError(detail)

    owns_store = finance_store is None
    if finance_store is None:
        store, storage_status = _open_store(runtime_settings)
    else:
        store = finance_store
        integrity = store.integrity()
        storage_status = (
            "ok"
            if integrity.lower() == "ok" and store.verify_audit_chain()[0]
            else "integrity check failed"
        )

    if safety_reviewer is not None:
        safety: SafetyReviewer = safety_reviewer
    elif isinstance(reasoner, SlaiFinancialReasoner):
        safety = SlaiSafetyReviewer(agent_provider=reasoner.agent_for)
    else:
        safety = NullSafetyReviewer()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if owns_reasoner:
                close_reasoner = getattr(reasoner, "close", None)
                if callable(close_reasoner):
                    result = close_reasoner()
                    if inspect.isawaitable(result):
                        await result

            if owns_store:
                try:
                    store.close()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Closing the ledger failed: %s", exc)

            if owns_gateway:
                for closable in (gateway, market_cache):
                    close_fn = getattr(closable, "close", None)
                    if callable(close_fn):
                        result = close_fn()
                        if inspect.isawaitable(result):
                            await result

    app = FastAPI(
        title="SLAIFI API",
        version=__version__,
        description="SLAI Financial Intelligence application API",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(runtime_settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID", "X-SLAIFI-Client"],
    )
    install_exception_handlers(app)
    if access_token:
        app.add_middleware(
            LocalAccessMiddleware,
            token=access_token,
            port=runtime_settings.api_port,
            security_headers=security_headers,
        )

    assets = tuple(AssetRef(symbol=symbol) for symbol in runtime_settings.market_overview_symbols)
    app.state.settings = runtime_settings
    app.state.financial_reasoner = reasoner
    app.state.market_data_provider = gateway
    app.state.market_history_service = GetMarketHistory(gateway=gateway)
    app.state.market_analysis_service = AnalyzeMarketSeries(reasoner=reasoner)
    app.state.portfolio_analysis_service = AnalyzePortfolio(reasoner=reasoner)
    app.state.goal_evaluation_service = EvaluateFinancialGoal(reasoner=reasoner)

    market_service = MarketDataService(gateway, max_bars=runtime_settings.api_max_market_bars)
    app.state.market_overview_service = GetMarketOverview(
        gateway=gateway, assets=assets, classify=market_service.resolve_asset
    )
    strategy_service = StrategyService(store)
    strategy_service.ensure_default()
    paper_service = PaperTradingService(
        store,
        market_service,
        strategy_service,
        policy=ExecutionPolicy(
            max_quote_age_seconds=runtime_settings.paper_max_quote_age_seconds,
            allow_closed_market=runtime_settings.paper_allow_closed_market_execution,
        ),
        storage_status=storage_status,
    )
    goal_tracker = GoalTracker(store, paper_service, strategy_service)
    recommendation_service = RecommendationService(
        market_service, strategy_service, paper_service, reasoner=reasoner, safety=safety
    )
    guidance_service = PortfolioGuidanceService(
        paper_service, strategy_service, goal_tracker, recommendation_service, market_service
    )
    app.state.finance_store = store
    app.state.storage_status = storage_status
    app.state.market_data_service = market_service
    app.state.strategy_service = strategy_service
    app.state.paper_service = paper_service
    app.state.goal_tracker = goal_tracker
    app.state.recommendation_service = recommendation_service
    app.state.guidance_service = guidance_service
    app.state.advisor_service = AdvisorService(
        store,
        strategy_service,
        goal_tracker,
        paper_service,
        recommendation_service,
        guidance_service,
        reasoner=reasoner,
        safety=safety,
    )
    app.include_router(api_router)
    ui_served = mount_frontend(app, runtime_settings.frontend_dist_dir)

    logger.info(
        "SLAIFI composition complete | env=%s | market_sources=%s | slai_enabled=%s | slai_quality=%s | ui=%s",
        runtime_settings.environment,
        ",".join(p.name for p in gateway.provider_status() if p.configured) or "none-configured",
        runtime_settings.slai_enabled,
        runtime_settings.slai_quality_enabled,
        "served" if ui_served else "not-built",
    )
    return app


_app: FastAPI | None = None


def __getattr__(name: str) -> FastAPI:
    """Build the ASGI ``app`` on first access (``uvicorn slaifi.main:app``), not at import.

    Importing this module must not open the ledger or touch the user's data folder.
    """

    global _app
    if name == "app":
        if _app is None:
            _app = create_app()
        return _app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
