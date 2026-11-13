"""Build the multi-source gateway from settings: one adapter per configured key."""

from __future__ import annotations

from collections.abc import Callable, Mapping

import httpx

from slaifi.core.config import Settings
from slaifi.domain.market import MarketCache
from slaifi.domain.market.gateway import ProviderPolicy
from slaifi.infrastructure.market_data.alpha_vantage_provider import AlphaVantageMarketDataProvider
from slaifi.infrastructure.market_data.base import HttpMarketProvider
from slaifi.infrastructure.market_data.finnhub_provider import FinnhubMarketDataProvider
from slaifi.infrastructure.market_data.fmp_provider import FmpMarketDataProvider
from slaifi.infrastructure.market_data.gateway import MultiSourceGateway
from slaifi.infrastructure.market_data.tiingo_provider import TiingoMarketDataProvider
from slaifi.infrastructure.market_data.twelve_data_provider import TwelveDataMarketDataProvider

PROVIDER_CLASSES: dict[str, type[HttpMarketProvider]] = {
    "twelvedata": TwelveDataMarketDataProvider,
    "tiingo": TiingoMarketDataProvider,
    "fmp": FmpMarketDataProvider,
    "finnhub": FinnhubMarketDataProvider,
    "alphavantage": AlphaVantageMarketDataProvider,
}

# Environment variable that holds each provider's key (for messages and documentation).
KEY_ENV = {name: f"SLAIFI_{name.upper()}_API_KEY" for name in PROVIDER_CLASSES}


def _custom_policy(base: ProviderPolicy, limits: Mapping[str, int]) -> ProviderPolicy:
    return ProviderPolicy(
        per_minute=limits.get("per_minute", base.per_minute),
        per_hour=limits.get("per_hour", base.per_hour),
        per_day=limits.get("per_day", base.per_day),
        note="Custom request limits (SLAIFI_MARKET_LIMITS); the provider's own limits still apply.",
        extra=base.extra,
    )


def build_provider(
    name: str,
    key: str,
    settings: Settings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> HttpMarketProvider:
    """One adapter for ``name`` using ``key`` (the single place an adapter is constructed)."""

    cls = PROVIDER_CLASSES[name]
    limits = settings.market_limits.get(name)
    kwargs: dict[str, object] = {
        "api_key": key,
        "policy": _custom_policy(cls.default_policy, limits) if limits else None,
        "base_url": settings.provider_base_url(name),
        "timeout_seconds": settings.market_http_timeout_seconds,
        "transport": transport,
    }
    if name == "twelvedata":
        kwargs["data_delay_minutes"] = settings.market_data_delay_minutes
    return cls(**kwargs)  # type: ignore[arg-type]


def build_gateway(
    settings: Settings,
    *,
    cache: MarketCache | None,
    transport: httpx.AsyncBaseTransport | None = None,
    key_for: Callable[[str], str | None] | None = None,
) -> MultiSourceGateway:
    """``key_for`` lets keys saved in Settings take part; by default only the environment is used."""

    resolve = key_for or settings.provider_key
    configured: list[HttpMarketProvider] = []
    missing: list[type[HttpMarketProvider]] = []
    for name in settings.provider_order:
        key = resolve(name)
        if key is None:
            missing.append(PROVIDER_CLASSES[name])
            continue
        configured.append(build_provider(name, key, settings, transport=transport))
    return MultiSourceGateway(
        configured,
        unconfigured=missing,
        cache=cache,
        quote_ttl_seconds=settings.market_quote_cache_ttl_seconds,
        history_ttl_seconds=settings.market_history_cache_ttl_seconds,
    )
