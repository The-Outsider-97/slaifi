"""Ordered failover across market-data providers with a last-known fallback.

Behaviour, in order, for every request:

1. try each configured provider that supports the request, in the configured priority order;
   a provider that is rate-limited, down or rejected is skipped (with a cool-down) and the
   next one is tried;
2. for history, a provider whose data does not reach back far enough is remembered but the
   search continues; the longest real series wins;
3. if every provider fails, serve the most recent *real* observation SLAIFI saved locally,
   flagged ``last_known`` with its original observation time;
4. if there is nothing saved either, return nothing. The UI shows NOT AVAILABLE.

Nothing is ever generated, interpolated or estimated.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

from slaifi.core.utils.errors import (
    MarketDataNotEntitledError,
    MarketDataRateLimitedError,
    MarketDataUnavailableError,
    SymbolNotFoundError,
)
from slaifi.domain.assets import AssetId
from slaifi.domain.market import (
    BarsFetch,
    FetchInfo,
    InstrumentInfo,
    MarketCache,
    OHLCVBar,
    PriceQuote,
    ProviderCheck,
    ProviderStatus,
    QuoteFetch,
    SearchFetch,
    SourceAttempt,
)
from slaifi.domain.market import gateway as g
from slaifi.infrastructure.market_data.base import HttpMarketProvider

DEFAULT_COOLDOWN_SECONDS = 30.0
RATE_LIMIT_COOLDOWN_SECONDS = 60.0
MAX_FUTURE_SKEW = timedelta(minutes=5)
VALID_INTERVALS = ("1min", "5min", "15min", "30min", "1h", "4h", "1day", "1week", "1month")
CHECK_SYMBOL = "AAPL"
# One daily/weekly/monthly request reaches back this far, so the 3M chart, the 1Y statistics and
# the 2Y recommendation share a single call. Free plans allow only a handful of calls a minute.
WIDE_HISTORY_DAYS = 760
WIDE_INTERVALS = ("1day", "1week", "1month")


@dataclass(slots=True)
class _Health:
    state: str = "ready"  # ready | cooling_down | rejected_credentials
    cooldown_until: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None


class MultiSourceGateway:
    """Implements :class:`MarketGateway` (and the plain provider calls older routes use)."""

    data_mode = "multi_source"

    def __init__(
        self,
        providers: Sequence[HttpMarketProvider],
        *,
        unconfigured: Sequence[type[HttpMarketProvider]] = (),
        cache: MarketCache | None = None,
        quote_ttl_seconds: float = 15.0,
        history_ttl_seconds: float = 300.0,
        clock: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._providers = list(providers)
        self._unconfigured = list(unconfigured)
        self._cache = cache
        self._quote_ttl = max(0.0, quote_ttl_seconds)
        self._history_ttl = max(0.0, history_ttl_seconds)
        self._now: Callable[[], datetime] = clock or (lambda: datetime.now(UTC))
        self._mono = monotonic
        self._health: dict[str, _Health] = {p.name: _Health() for p in self._providers}
        self._quotes: dict[AssetId, tuple[float, QuoteFetch]] = {}
        # (symbol, exchange, interval) -> (monotonic time, fetched from, fetched to, result)
        self._bars: dict[
            tuple[str, str | None, str], tuple[float, datetime, datetime, BarsFetch]
        ] = {}

    # ------------------------------------------------------------------ introspection
    @property
    def configured(self) -> bool:
        return bool(self._providers)

    @property
    def supported_intervals(self) -> tuple[str, ...]:
        offered = {i for p in self._providers for i in p.supported_intervals}
        return tuple(i for i in VALID_INTERVALS if i in offered)

    @property
    def source_name(self) -> str:
        return "+".join(p.name for p in self._providers) or "none"

    def provider_status(self) -> Sequence[ProviderStatus]:
        rows: list[ProviderStatus] = []
        now = self._now()
        for p in self._providers:
            h = self._health[p.name]
            state = h.state
            if state == "cooling_down" and (h.cooldown_until is None or h.cooldown_until <= now):
                state = "ready"
            minute, day = p.budget.counts()
            rows.append(
                ProviderStatus(
                    name=p.name,
                    label=p.label,
                    configured=True,
                    capabilities=p.capabilities,
                    intervals=p.supported_intervals,
                    state=state,
                    cooldown_until=h.cooldown_until if state == "cooling_down" else None,
                    last_success_at=h.last_success_at,
                    last_error=h.last_error,
                    last_error_at=h.last_error_at,
                    calls_last_minute=minute,
                    calls_today=day,
                    free_tier_note=p.policy.note,
                )
            )
        for cls in self._unconfigured:
            rows.append(
                ProviderStatus(
                    name=cls.name,
                    label=cls.label,
                    configured=False,
                    capabilities=cls.capabilities,
                    intervals=cls.supported_intervals,
                    state="not_configured",
                    free_tier_note=cls.default_policy.note,
                )
            )
        return rows

    @property
    def providers(self) -> tuple[HttpMarketProvider, ...]:
        return tuple(self._providers)

    async def replace_providers(
        self,
        providers: Sequence[HttpMarketProvider],
        unconfigured: Sequence[type[HttpMarketProvider]] = (),
    ) -> None:
        """Swap the configured sources (a key was added, changed or removed in Settings).

        An adapter that is kept keeps its health and request budget; a new one starts fresh, so a
        corrected key is not held back by an earlier rejection. Cached real data stays valid.
        """

        previous = self._providers
        self._providers = list(providers)
        self._unconfigured = list(unconfigured)
        self._health = {p.name: self._health.get(p.name, _Health()) for p in self._providers}
        for p in self._providers:
            if p not in previous:
                self._health[p.name] = _Health()
        for p in previous:
            if p not in self._providers:
                await p.close()

    async def close(self) -> None:
        for p in self._providers:
            await p.close()

    # ------------------------------------------------------------------ attempt machinery
    async def _call(
        self, provider: HttpMarketProvider, run: Callable[[], Awaitable[Any]]
    ) -> tuple[Any, SourceAttempt]:
        name = provider.name
        h = self._health[name]
        now = self._now()
        if h.state == "rejected_credentials":
            return None, SourceAttempt(name, g.OUTCOME_UNAUTHORIZED, "API key was rejected earlier")
        if h.cooldown_until is not None and now < h.cooldown_until:
            remaining = int((h.cooldown_until - now).total_seconds())
            return None, SourceAttempt(
                name,
                g.OUTCOME_COOLING_DOWN,
                f"skipped for another {max(remaining, 1)} s: {h.last_error}",
            )
        try:
            result = await run()
        except MarketDataRateLimitedError as exc:
            wait = exc.retry_after_seconds or RATE_LIMIT_COOLDOWN_SECONDS
            self._fail(h, now, exc.message, cooldown=wait)
            return None, SourceAttempt(name, g.OUTCOME_RATE_LIMITED, exc.message)
        except MarketDataNotEntitledError as exc:
            return None, SourceAttempt(name, g.OUTCOME_UNSUPPORTED, exc.message)
        except SymbolNotFoundError as exc:
            return None, SourceAttempt(name, g.OUTCOME_NOT_FOUND, exc.message)
        except MarketDataUnavailableError as exc:
            if exc.retryable is False:
                h.state = "rejected_credentials"
                h.last_error, h.last_error_at = exc.message, now
                return None, SourceAttempt(name, g.OUTCOME_UNAUTHORIZED, exc.message)
            self._fail(h, now, exc.message, cooldown=DEFAULT_COOLDOWN_SECONDS)
            return None, SourceAttempt(name, g.OUTCOME_UNAVAILABLE, exc.message)
        except Exception as exc:  # noqa: BLE001 - one broken adapter must not stop the others
            message = f"{provider.label} failed unexpectedly ({type(exc).__name__})"
            self._fail(h, now, message, cooldown=DEFAULT_COOLDOWN_SECONDS)
            return None, SourceAttempt(name, g.OUTCOME_UNAVAILABLE, message)
        h.state, h.cooldown_until, h.last_success_at = "ready", None, now
        return result, SourceAttempt(name, g.OUTCOME_OK)

    def _fail(self, h: _Health, now: datetime, message: str, *, cooldown: float) -> None:
        h.state = "cooling_down"
        h.cooldown_until = now + timedelta(seconds=cooldown)
        h.last_error, h.last_error_at = message, now

    def _capable(self, capability: str, interval: str | None = None) -> list[HttpMarketProvider]:
        return [
            p
            for p in self._providers
            if capability in p.capabilities
            and (interval is None or interval in p.supported_intervals)
        ]

    def _remember_quote(self, quote: PriceQuote) -> None:
        cache = self._cache
        if cache is None:
            return
        try:
            cache.save_quote(quote, saved_at=self._now())
        except Exception:  # noqa: BLE001 - a cache problem must never break live data
            return

    def _remember_bars(
        self, asset: AssetId, interval: str, bars: Sequence[OHLCVBar], source: str
    ) -> None:
        cache = self._cache
        if cache is None:
            return
        try:
            cache.save_bars(asset, interval, bars, source=source, saved_at=self._now())
        except Exception:  # noqa: BLE001
            return

    def _remember_search(self, query: str, results: Sequence[InstrumentInfo], source: str) -> None:
        cache = self._cache
        if cache is None:
            return
        try:
            cache.save_search(query, results, source=source, saved_at=self._now())
        except Exception:  # noqa: BLE001
            return

    # ------------------------------------------------------------------ quotes
    async def fetch_quotes(self, assets: Sequence[AssetId]) -> Sequence[QuoteFetch]:
        return tuple(await asyncio.gather(*(self._quote_one(a) for a in assets)))

    async def _quote_one(self, asset: AssetId) -> QuoteFetch:
        hit = self._quotes.get(asset)
        if hit is not None and self._mono() - hit[0] <= self._quote_ttl:
            return hit[1]
        attempts: list[SourceAttempt] = []
        for provider in self._capable("quotes"):
            result, attempt = await self._call(provider, partial(provider.get_quotes, [asset]))
            if attempt.outcome == g.OUTCOME_OK and not result:
                attempt = SourceAttempt(provider.name, g.OUTCOME_EMPTY, "no quote for this symbol")
            attempts.append(attempt)
            if not result:
                continue
            quote: PriceQuote = result[0]
            if quote.observed_at > self._now() + MAX_FUTURE_SKEW:
                attempts[-1] = SourceAttempt(
                    provider.name, g.OUTCOME_UNAVAILABLE, "quote time is in the future; ignored"
                )
                continue
            quote = replace(quote, asset=asset, last_known=False)
            fetch = QuoteFetch(asset, quote, FetchInfo(provider.name, attempts=tuple(attempts)))
            self._remember_quote(quote)
            if self._quote_ttl > 0:
                self._quotes[asset] = (self._mono(), fetch)
            return fetch
        if self._cache is not None:
            try:
                loaded = self._cache.load_quote(asset)
            except Exception:  # noqa: BLE001
                loaded = None
            if loaded is not None:
                stored, saved_at = loaded
                quote = replace(stored, asset=asset, last_known=True)
                return QuoteFetch(
                    asset, quote, FetchInfo(stored.source, True, saved_at, tuple(attempts))
                )
        return QuoteFetch(asset, None, FetchInfo(None, attempts=tuple(attempts)))

    # ------------------------------------------------------------------ history
    @staticmethod
    def _covers(bars: Sequence[OHLCVBar], start_at: datetime) -> bool:
        """Does the series reach back to (about) the requested start?"""

        if not bars:
            return False
        step = bars[0].end_at - bars[0].start_at
        tolerance = max(timedelta(days=10), step * 3)
        return bars[0].start_at <= start_at + tolerance

    async def fetch_bars(
        self, asset: AssetId, *, start_at: datetime, end_at: datetime, interval: str = "1day"
    ) -> BarsFetch:
        key = (asset.symbol, asset.exchange, interval)
        hit = self._bars.get(key)
        if (
            hit is not None
            and self._mono() - hit[0] <= self._history_ttl
            and hit[1] <= start_at
            and hit[2] >= end_at - timedelta(days=1)
        ):
            return self._window(hit[3], start_at, end_at, interval)
        fetch_start = start_at
        if interval in WIDE_INTERVALS:
            fetch_start = min(start_at, end_at - timedelta(days=WIDE_HISTORY_DAYS))
        attempts: list[SourceAttempt] = []
        best: tuple[tuple[OHLCVBar, ...], str] | None = None
        for provider in self._capable("bars", interval):
            result, attempt = await self._call(
                provider,
                partial(
                    provider.get_bars, asset, start_at=fetch_start, end_at=end_at, interval=interval
                ),
            )
            bars = tuple(result or ())
            if attempt.outcome == g.OUTCOME_OK and not bars:
                attempt = SourceAttempt(provider.name, g.OUTCOME_EMPTY, "no bars for this range")
            elif attempt.outcome == g.OUTCOME_OK and not self._covers(bars, start_at):
                attempt = SourceAttempt(
                    provider.name,
                    g.OUTCOME_OK,
                    f"partial history ({len(bars)} bars from {bars[0].start_at:%Y-%m-%d}); trying others",
                )
            attempts.append(attempt)
            if not bars:
                continue
            self._remember_bars(asset, interval, bars, provider.name)
            if self._covers(bars, start_at):
                best = (bars, provider.name)
                break
            if best is None or len(bars) > len(best[0]):
                best = (bars, provider.name)
        if best is not None:
            fetch = BarsFetch(best[0], FetchInfo(best[1], attempts=tuple(attempts)))
            if self._history_ttl > 0:
                self._bars[key] = (self._mono(), fetch_start, end_at, fetch)
            return self._window(fetch, start_at, end_at, interval)
        if self._cache is not None:
            try:
                saved, source, saved_at = self._cache.load_bars(
                    asset, interval, start_at=start_at, end_at=end_at
                )
            except Exception:  # noqa: BLE001
                saved, source, saved_at = (), None, None
            if saved:
                return BarsFetch(saved, FetchInfo(source, True, saved_at, tuple(attempts)))
        return BarsFetch((), FetchInfo(None, attempts=tuple(attempts)))

    @staticmethod
    def _window(
        fetch: BarsFetch, start_at: datetime, end_at: datetime, interval: str = "1day"
    ) -> BarsFetch:
        if interval in WIDE_INTERVALS:  # providers filter daily history by calendar date
            start_at = start_at.replace(hour=0, minute=0, second=0, microsecond=0)
        inside = tuple(b for b in fetch.bars if start_at <= b.start_at <= end_at)
        return BarsFetch(inside, fetch.info)

    # ------------------------------------------------------------------ search
    async def fetch_search(
        self, query: str, *, limit: int = 10, prefer_saved: bool = False
    ) -> SearchFetch:
        """Search instruments. ``prefer_saved`` reuses an earlier exact match to save API calls."""

        attempts: list[SourceAttempt] = []
        if prefer_saved and self._cache is not None:
            try:
                loaded = self._cache.load_search(query)
            except Exception:  # noqa: BLE001
                loaded = None
            if loaded is not None and any(
                i.asset.symbol == query.strip().upper() for i in loaded[0]
            ):
                results, source, saved_at = loaded
                return SearchFetch(results[:limit], FetchInfo(source, True, saved_at, ()))
        for provider in self._capable("search"):
            result, attempt = await self._call(
                provider, partial(provider.search_instruments, query, limit=limit)
            )
            found: tuple[InstrumentInfo, ...] = tuple(result or ())
            if attempt.outcome == g.OUTCOME_OK and not found:
                attempt = SourceAttempt(provider.name, g.OUTCOME_EMPTY, "no matches")
            attempts.append(attempt)
            if found:
                self._remember_search(query, found, provider.name)
                return SearchFetch(found, FetchInfo(provider.name, attempts=tuple(attempts)))
        if self._cache is not None and any(a.outcome != g.OUTCOME_OK for a in attempts):
            try:
                loaded = self._cache.load_search(query)
            except Exception:  # noqa: BLE001
                loaded = None
            if loaded is not None:
                results, source, saved_at = loaded
                return SearchFetch(
                    results[:limit], FetchInfo(source, True, saved_at, tuple(attempts))
                )
        return SearchFetch((), FetchInfo(None, attempts=tuple(attempts)))

    # ------------------------------------------------------------------ checks
    async def check_providers(self, only: str | None = None) -> Sequence[ProviderCheck]:
        """Make one real quote request per configured provider (used by Settings → Check).

        ``only`` limits the check to one source, so saving a key does not spend the others' free requests.
        """

        checks: list[ProviderCheck] = []
        probe = AssetId(CHECK_SYMBOL)
        for p in self._providers:
            if only is not None and p.name != only:
                continue
            started = time.perf_counter()
            result, attempt = await self._call(p, partial(p.get_quotes, [probe]))
            latency = (time.perf_counter() - started) * 1000.0
            if attempt.outcome == g.OUTCOME_OK and result:
                q: PriceQuote = result[0]
                checks.append(
                    ProviderCheck(
                        p.name,
                        True,
                        True,
                        f"OK: {CHECK_SYMBOL} {q.price} {q.currency} observed {q.observed_at:%Y-%m-%d %H:%M} UTC",
                        latency,
                    )
                )
            elif attempt.outcome == g.OUTCOME_OK:
                checks.append(
                    ProviderCheck(
                        p.name,
                        True,
                        True,
                        "Key accepted and the service answered, but it returned no quote for AAPL.",
                        latency,
                    )
                )
            else:
                checks.append(
                    ProviderCheck(
                        p.name, True, False, f"{attempt.outcome}: {attempt.detail}", latency
                    )
                )
        for cls in self._unconfigured:
            if only is None or cls.name == only:
                checks.append(ProviderCheck(cls.name, False, False, "No API key configured."))
        return checks

    # ------------------------------------------------------------------ plain provider calls
    async def get_quotes(self, assets: Sequence[AssetId]) -> Sequence[PriceQuote]:
        return tuple(f.quote for f in await self.fetch_quotes(assets) if f.quote is not None)

    async def get_bars(
        self, asset: AssetId, *, start_at: datetime, end_at: datetime, interval: str = "1day"
    ) -> Sequence[OHLCVBar]:
        return (
            await self.fetch_bars(asset, start_at=start_at, end_at=end_at, interval=interval)
        ).bars

    async def search_instruments(self, query: str, *, limit: int = 10) -> Sequence[InstrumentInfo]:
        return (await self.fetch_search(query, limit=limit)).results
