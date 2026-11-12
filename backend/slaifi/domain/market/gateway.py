"""Multi-source market-data contract: results that say where data came from and how fresh it is.

A *provider* talks to one external service. A *gateway* combines several providers and a local
cache of the last real observations. Its results never contain invented data: when every
source fails the result is empty and says why, and the UI shows NOT AVAILABLE.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from slaifi.domain.assets import AssetId
from slaifi.domain.market.models import InstrumentInfo, OHLCVBar, PriceQuote

# Outcomes of one attempt against one source.
OUTCOME_OK = "ok"
OUTCOME_EMPTY = "empty"  # the source answered but has no data for this request
OUTCOME_RATE_LIMITED = "rate_limited"
OUTCOME_UNAVAILABLE = "unavailable"
OUTCOME_UNAUTHORIZED = "unauthorized"
OUTCOME_NOT_FOUND = "not_found"
OUTCOME_UNSUPPORTED = "unsupported"
OUTCOME_COOLING_DOWN = "cooling_down"


@dataclass(frozen=True, slots=True)
class SourceAttempt:
    source: str
    outcome: str
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class FetchInfo:
    """Where a result came from.

    ``source`` is the provider that originally supplied the data (also for last-known data).
    ``saved_at`` is set only for ``last_known`` results: when SLAIFI stored them locally.
    """

    source: str | None
    last_known: bool = False
    saved_at: datetime | None = None
    attempts: tuple[SourceAttempt, ...] = ()


@dataclass(frozen=True, slots=True)
class QuoteFetch:
    asset: AssetId
    quote: PriceQuote | None
    info: FetchInfo


@dataclass(frozen=True, slots=True)
class BarsFetch:
    bars: tuple[OHLCVBar, ...]
    info: FetchInfo


@dataclass(frozen=True, slots=True)
class SearchFetch:
    results: tuple[InstrumentInfo, ...]
    info: FetchInfo


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    """Operational state of one configured (or unconfigured) source. Never contains a key."""

    name: str
    label: str
    configured: bool
    capabilities: tuple[str, ...]
    intervals: tuple[str, ...]
    state: str  # ready | cooling_down | rejected_credentials | not_configured
    cooldown_until: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None
    calls_last_minute: int = 0
    calls_today: int = 0
    free_tier_note: str = ""


@dataclass(frozen=True, slots=True)
class ProviderCheck:
    name: str
    configured: bool
    ok: bool
    detail: str
    latency_ms: float | None = None


class MarketCache(Protocol):
    """Durable store of the last real observations (never of generated data)."""

    def save_quote(self, quote: PriceQuote, *, saved_at: datetime) -> None: ...

    def load_quote(self, asset: AssetId) -> tuple[PriceQuote, datetime] | None: ...

    def save_bars(
        self,
        asset: AssetId,
        interval: str,
        bars: Sequence[OHLCVBar],
        *,
        source: str,
        saved_at: datetime,
    ) -> None: ...

    def load_bars(
        self, asset: AssetId, interval: str, *, start_at: datetime, end_at: datetime
    ) -> tuple[tuple[OHLCVBar, ...], str | None, datetime | None]: ...

    def save_search(
        self, query: str, results: Sequence[InstrumentInfo], *, source: str, saved_at: datetime
    ) -> None: ...

    def load_search(
        self, query: str
    ) -> tuple[tuple[InstrumentInfo, ...], str, datetime] | None: ...


class MarketGateway(Protocol):
    """What the application asks of market data."""

    @property
    def supported_intervals(self) -> tuple[str, ...]: ...

    async def fetch_quotes(self, assets: Sequence[AssetId]) -> Sequence[QuoteFetch]: ...

    async def fetch_bars(
        self, asset: AssetId, *, start_at: datetime, end_at: datetime, interval: str = "1day"
    ) -> BarsFetch: ...

    async def fetch_search(
        self, query: str, *, limit: int = 10, prefer_saved: bool = False
    ) -> SearchFetch: ...

    def provider_status(self) -> Sequence[ProviderStatus]: ...

    async def check_providers(self) -> Sequence[ProviderCheck]: ...


@dataclass(frozen=True, slots=True)
class ProviderPolicy:
    """Free-tier budget a provider adapter enforces on itself before calling out."""

    per_minute: int | None = None
    per_hour: int | None = None
    per_day: int | None = None
    note: str = ""
    extra: Mapping[str, str] = field(default_factory=dict)
