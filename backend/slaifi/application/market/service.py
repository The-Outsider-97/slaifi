"""Market-data application service: search, quotes, history, statistics and comparison.

Every result carries :class:`DataProvenance`, so callers (and the UI) can always tell live from
delayed, a fresh provider answer from the last known value, and how old an observation is.
Nothing is interpolated or invented: when no provider and no saved observation can supply data
the result says so (mode ``unavailable``) and the UI shows NOT AVAILABLE.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from statistics import mean

from slaifi.core.utils.errors import ValidationError
from slaifi.domain.assets import AssetClass, AssetId
from slaifi.domain.market import (
    FetchInfo,
    InstrumentInfo,
    MarketGateway,
    OHLCVBar,
    PriceQuote,
    ProviderCheck,
    ProviderStatus,
    SourceAttempt,
)
from slaifi.engines.features import simple_returns
from slaifi.engines.risk import historical_volatility, maximum_drawdown, pearson_correlation
from slaifi.engines.technical import BarQuality, assess_bars, normalize_bars, rsi, sma
from slaifi.engines.utils.errors import (
    EngineValidationError,
    FinancialCalculationError,
    InsufficientDataError,
)

PERIODS_PER_YEAR = {"1day": 252, "1week": 52, "1month": 12}
VALID_INTERVALS = ("1min", "5min", "15min", "30min", "1h", "4h", "1day", "1week", "1month")
MAX_COMPARE_SYMBOLS = 6
MAX_RANGE_DAYS = 3650

MODE_LIVE = "live"
MODE_DELAYED = "delayed"
MODE_UNCONFIRMED = "live_delay_unknown"
MODE_RETRIEVED = "retrieved"
MODE_LAST_KNOWN = "last_known"
MODE_UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class DataProvenance:
    mode: str  # live | delayed | live_delay_unknown | retrieved | last_known | unavailable
    source: str | None
    observed_at: datetime | None
    retrieved_at: datetime
    age_seconds: float | None
    delayed: bool | None
    market_open: bool | None
    last_known: bool = False
    saved_at: datetime | None = None
    attempts: tuple[SourceAttempt, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        return self.mode != MODE_UNAVAILABLE


@dataclass(frozen=True, slots=True)
class QuoteView:
    asset: AssetId
    quote: PriceQuote | None
    provenance: DataProvenance


@dataclass(frozen=True, slots=True)
class SearchView:
    query: str
    results: tuple[InstrumentInfo, ...]
    provenance: DataProvenance
    supported: bool


@dataclass(frozen=True, slots=True)
class HistoryView:
    asset: AssetId
    interval: str
    bars: tuple[OHLCVBar, ...]
    quality: BarQuality
    provenance: DataProvenance
    overlays: dict[str, tuple[float | None, ...]] = field(default_factory=dict)
    requested_days: int = 0
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HistoryStats:
    asset: AssetId
    interval: str
    observation_count: int
    start_at: datetime | None
    end_at: datetime | None
    first_close: float | None
    last_close: float | None
    period_return: float | None
    annualized_volatility: float | None
    max_drawdown: float | None
    current_drawdown: float | None
    period_high: float | None
    period_low: float | None
    average_volume: float | None
    best_period_return: float | None
    worst_period_return: float | None
    sma_20: float | None
    sma_50: float | None
    rsi_14: float | None
    periods_per_year: int | None
    provenance: DataProvenance
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ComparisonSeries:
    asset: AssetId
    indexed: tuple[float, ...]  # rebased to 100 at the first common bar
    period_return: float | None
    annualized_volatility: float | None
    max_drawdown: float | None


@dataclass(frozen=True, slots=True)
class ComparisonView:
    interval: str
    timestamps: tuple[datetime, ...]
    series: tuple[ComparisonSeries, ...]
    correlations: dict[str, dict[str, float | None]]
    provenance: DataProvenance
    notes: tuple[str, ...] = ()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _failure_note(attempts: Sequence[SourceAttempt]) -> str | None:
    problems = [
        f"{a.source}: {a.detail or a.outcome}"
        for a in attempts
        if a.outcome not in ("ok",) and (a.detail or a.outcome)
    ]
    return "; ".join(problems) if problems else None


_US_COUNTRIES = {"united states", "us", "usa"}
_US_EXCHANGES = {
    "NYSE",
    "NASDAQ",
    "NYSE ARCA",
    "NYSEARCA",
    "ARCA",
    "AMEX",
    "NYSE AMERICAN",
    "BATS",
    "CBOE",
}


def _is_us_listing(info: InstrumentInfo) -> bool:
    country = (info.country or "").strip().lower()
    exchange = (info.asset.exchange or "").strip().upper()
    return country in _US_COUNTRIES or exchange in _US_EXCHANGES


class MarketDataService:
    """Facade over a :class:`MarketGateway` adding provenance, validation and statistics."""

    def __init__(
        self,
        gateway: MarketGateway,
        *,
        clock: Callable[[], datetime] = _utc_now,
        max_bars: int = 5000,
    ) -> None:
        self._gateway = gateway
        self._clock = clock
        self._max_bars = max_bars
        self._resolved: dict[tuple[str, str | None, str | None], AssetId] = {}

    @property
    def supported_intervals(self) -> tuple[str, ...]:
        """Intervals at least one configured provider can serve (never more than the API accepts)."""

        offered = tuple(self._gateway.supported_intervals)
        return tuple(i for i in VALID_INTERVALS if i in offered) or ("1day",)

    @property
    def configured(self) -> bool:
        return bool(getattr(self._gateway, "configured", True))

    def provider_status(self) -> Sequence[ProviderStatus]:
        return self._gateway.provider_status()

    async def check_providers(self, only: str | None = None) -> Sequence[ProviderCheck]:
        return await self._gateway.check_providers(only)

    @property
    def data_mode(self) -> str:
        return "live" if self.configured else MODE_UNAVAILABLE

    # ------------------------------------------------------------------ provenance
    def provenance(
        self,
        info: FetchInfo | None = None,
        *,
        has_data: bool = True,
        observed_at: datetime | None = None,
        market_open: bool | None = None,
        delayed: bool | None = None,
        kind: str = "history",
        notes: Sequence[str] = (),
    ) -> DataProvenance:
        """Describe where a result came from. ``kind`` is ``quote`` or ``history``."""

        now = self._clock()
        attempts = info.attempts if info is not None else ()
        collected = list(notes)
        problem = _failure_note(attempts)
        age = max(0.0, (now - observed_at).total_seconds()) if observed_at else None
        if not has_data:
            if not self.configured:
                collected.append(
                    "No market-data provider is configured. Add at least one free API key "
                    "(see Settings)."
                )
            elif problem:
                collected.append(f"No provider could supply this data ({problem}).")
            else:
                collected.append("No provider has data for this request.")
            return DataProvenance(
                mode=MODE_UNAVAILABLE,
                source=None,
                observed_at=None,
                retrieved_at=now,
                age_seconds=None,
                delayed=None,
                market_open=None,
                attempts=attempts,
                notes=tuple(collected),
            )
        source = info.source if info is not None else None
        if info is not None and info.last_known:
            saved = info.saved_at
            when = f", saved {saved:%Y-%m-%d %H:%M} UTC" if saved else ""
            collected.append(
                f"Last known data{when}; originally from {source or 'an earlier session'}. "
                "Live providers could not supply it right now"
                + (f" ({problem})." if problem else ".")
            )
            return DataProvenance(
                mode=MODE_LAST_KNOWN,
                source=source,
                observed_at=observed_at,
                retrieved_at=now,
                age_seconds=age,
                delayed=None,
                market_open=market_open,
                last_known=True,
                saved_at=saved,
                attempts=attempts,
                notes=tuple(collected),
            )
        if kind == "quote":
            if delayed is True:
                mode = MODE_DELAYED
                collected.append("Quotes from this feed are delayed.")
            elif delayed is False:
                mode = MODE_LIVE
            else:
                mode = MODE_UNCONFIRMED
                collected.append("The feed's delay is not known; do not assume real-time prices.")
        else:
            mode = MODE_RETRIEVED
        if market_open is False:
            collected.append("The market is closed: the price is the last observation.")
        return DataProvenance(
            mode=mode,
            source=source,
            observed_at=observed_at,
            retrieved_at=now,
            age_seconds=age,
            delayed=delayed,
            market_open=market_open,
            attempts=attempts,
            notes=tuple(collected),
        )

    def _quote_provenance(self, quote: PriceQuote | None, info: FetchInfo) -> DataProvenance:
        if quote is None:
            return self.provenance(info, has_data=False, kind="quote")
        return self.provenance(
            info,
            observed_at=quote.observed_at,
            market_open=quote.is_market_open,
            delayed=quote.delayed,
            kind="quote",
        )

    # ------------------------------------------------------------------ search & resolution
    async def search(self, query: str, *, limit: int = 10) -> SearchView:
        text = query.strip()
        if not text:
            raise ValidationError("search query must not be empty")
        if len(text) > 64:
            raise ValidationError("search query is too long")
        fetch = await self._gateway.fetch_search(text, limit=max(1, min(limit, 25)))
        results = tuple(fetch.results)
        return SearchView(
            text,
            results,
            self.provenance(fetch.info, has_data=bool(results), kind="history"),
            True,
        )

    async def resolve_asset(
        self,
        symbol: str,
        *,
        exchange: str | None = None,
        asset_class: AssetClass | None = None,
    ) -> AssetId:
        """Return the best identified asset (class, exchange, currency) for a user-supplied symbol.

        Identification is best effort: when no provider can search, the symbol is used as given
        and later lookups simply report NOT AVAILABLE if the instrument cannot be found.
        """

        text = symbol.strip().upper()
        if not text or len(text) > 24:
            raise ValidationError("symbol must be 1-24 characters")
        key = (
            text,
            exchange.upper() if exchange else None,
            asset_class.value if asset_class else None,
        )
        cached = self._resolved.get(key)
        if cached is not None:
            return cached
        found: AssetId | None = None
        try:
            fetch = await self._gateway.fetch_search(text, limit=10, prefer_saved=True)
            hits = fetch.results
        except Exception:  # noqa: BLE001 - resolution is best effort; data calls report their own failures
            hits = ()
        exact = [h for h in hits if h.asset.symbol == text]
        # The same ticker can exist on several exchanges (and currencies). US listings first.
        exact.sort(key=lambda h: 0 if _is_us_listing(h) else 1)
        if exchange:
            exact = [h for h in exact if (h.asset.exchange or "").upper() == exchange.upper()]
        if asset_class and asset_class is not AssetClass.UNKNOWN:
            exact = [h for h in exact if h.asset.asset_class is asset_class]
        if exact:
            found = exact[0].asset
        if found is None:
            found = AssetId(
                text, asset_class or AssetClass.UNKNOWN, exchange.upper() if exchange else None
            )
        else:
            self._resolved[key] = found
        return found

    # ------------------------------------------------------------------ quotes
    async def quote(self, asset: AssetId) -> QuoteView:
        return (await self.quotes([asset]))[0]

    async def quotes(self, assets: Sequence[AssetId]) -> list[QuoteView]:
        if not assets:
            return []
        fetched = await self._gateway.fetch_quotes(list(assets))
        return [
            QuoteView(f.asset, f.quote, self._quote_provenance(f.quote, f.info)) for f in fetched
        ]

    # ------------------------------------------------------------------ history
    async def history(
        self,
        asset: AssetId,
        *,
        days: int = 365,
        interval: str = "1day",
        end_at: datetime | None = None,
        overlays: Sequence[str] = (),
    ) -> HistoryView:
        if interval not in VALID_INTERVALS:
            raise ValidationError(f"interval must be one of {', '.join(VALID_INTERVALS)}")
        if not 1 <= days <= MAX_RANGE_DAYS:
            raise ValidationError(f"days must be between 1 and {MAX_RANGE_DAYS}")
        end = end_at or self._clock()
        start = end - timedelta(days=days)
        fetch = await self._gateway.fetch_bars(asset, start_at=start, end_at=end, interval=interval)
        bars, duplicates, reordered = normalize_bars(tuple(fetch.bars))
        notes: list[str] = []
        if duplicates:
            notes.append(f"{duplicates} duplicate bar(s) were removed.")
        if reordered:
            notes.append("The provider returned bars out of order; they were sorted.")
        if len(bars) > self._max_bars:
            notes.append(f"Only the latest {self._max_bars} bars are shown.")
            bars = bars[-self._max_bars :]
        quality = assess_bars(bars, interval)
        if not bars and interval not in self.supported_intervals:
            notes.append(
                f"{interval} bars are not offered by the configured data sources; "
                f"they provide: {', '.join(self.supported_intervals)}."
            )
        elif bars and quality.gap_count:
            notes.append(
                f"The series contains {quality.gap_count} gap(s); missing bars are not filled in."
            )
        series: dict[str, tuple[float | None, ...]] = {}
        closes = [float(b.close) for b in bars]
        for name in overlays:
            try:
                if name == "sma20":
                    series[name] = sma(closes, 20)
                elif name == "sma50":
                    series[name] = sma(closes, 50)
                elif name == "rsi14":
                    series[name] = rsi(closes, 14)
                else:
                    raise ValidationError(f"unknown overlay {name!r}")
            except InsufficientDataError:
                series[name] = (None,) * len(closes)
        last_time = bars[-1].end_at if bars else None
        return HistoryView(
            asset=asset,
            interval=interval,
            bars=bars,
            quality=quality,
            provenance=self.provenance(
                fetch.info, has_data=bool(bars), observed_at=last_time, kind="history"
            ),
            overlays=series,
            requested_days=days,
            notes=tuple(notes),
        )

    # ------------------------------------------------------------------ statistics
    async def stats(
        self, asset: AssetId, *, days: int = 365, interval: str = "1day"
    ) -> HistoryStats:
        view = await self.history(asset, days=days, interval=interval)
        return self.stats_from_view(view)

    def stats_from_view(self, view: HistoryView) -> HistoryStats:
        bars = view.bars
        notes = list(view.notes)
        periods = PERIODS_PER_YEAR.get(view.interval)
        if len(bars) < 2:
            return HistoryStats(
                asset=view.asset,
                interval=view.interval,
                observation_count=len(bars),
                start_at=None,
                end_at=None,
                first_close=None,
                last_close=None,
                period_return=None,
                annualized_volatility=None,
                max_drawdown=None,
                current_drawdown=None,
                period_high=None,
                period_low=None,
                average_volume=None,
                best_period_return=None,
                worst_period_return=None,
                sma_20=None,
                sma_50=None,
                rsi_14=None,
                periods_per_year=periods,
                provenance=view.provenance,
                notes=tuple([*notes, "At least two bars are needed for statistics."]),
            )
        closes = [float(b.close) for b in bars]
        returns = [r for r in simple_returns(closes) if r is not None]
        volatility = None
        if periods is not None and len(returns) >= 2:
            volatility = historical_volatility(returns, periods_per_year=periods)
        elif periods is None:
            notes.append("Volatility is not annualised for intraday intervals.")
        high = max(closes)
        low = min(closes)

        def last(values: tuple[float | None, ...]) -> float | None:
            return values[-1] if values else None

        sma20 = sma(closes, 20) if len(closes) >= 20 else None
        sma50 = sma(closes, 50) if len(closes) >= 50 else None
        rsi14 = rsi(closes, 14) if len(closes) >= 15 else None
        return HistoryStats(
            asset=view.asset,
            interval=view.interval,
            observation_count=len(bars),
            start_at=bars[0].start_at,
            end_at=bars[-1].end_at,
            first_close=closes[0],
            last_close=closes[-1],
            period_return=closes[-1] / closes[0] - 1.0,
            annualized_volatility=volatility,
            max_drawdown=maximum_drawdown(closes),
            current_drawdown=closes[-1] / high - 1.0,
            period_high=high,
            period_low=low,
            average_volume=float(mean(float(b.volume) for b in bars)),
            best_period_return=max(returns) if returns else None,
            worst_period_return=min(returns) if returns else None,
            sma_20=last(sma20) if sma20 else None,
            sma_50=last(sma50) if sma50 else None,
            rsi_14=last(rsi14) if rsi14 else None,
            periods_per_year=periods,
            provenance=view.provenance,
            notes=tuple(notes),
        )

    def _merge_provenance(self, parts: Sequence[DataProvenance]) -> DataProvenance:
        """One provenance for a multi-instrument result: the weakest member decides the label."""

        usable = [p for p in parts if p.available]
        if not usable:
            return parts[0] if parts else self.provenance(has_data=False)
        weakest = next((p for p in usable if p.last_known), usable[0])
        notes = tuple(dict.fromkeys(n for p in parts for n in p.notes))
        sources = "+".join(dict.fromkeys(p.source for p in usable if p.source)) or None
        observed = [p.observed_at for p in usable if p.observed_at]
        return DataProvenance(
            mode=weakest.mode,
            source=sources,
            observed_at=min(observed) if observed else None,
            retrieved_at=weakest.retrieved_at,
            age_seconds=max((p.age_seconds or 0.0) for p in usable),
            delayed=weakest.delayed,
            market_open=weakest.market_open,
            last_known=any(p.last_known for p in usable),
            saved_at=weakest.saved_at,
            attempts=tuple(a for p in parts for a in p.attempts),
            notes=notes,
        )

    # ------------------------------------------------------------------ comparison
    async def compare(
        self, assets: Sequence[AssetId], *, days: int = 365, interval: str = "1day"
    ) -> ComparisonView:
        unique = list(dict.fromkeys(assets))
        if not 2 <= len(unique) <= MAX_COMPARE_SYMBOLS:
            raise ValidationError(f"compare between 2 and {MAX_COMPARE_SYMBOLS} distinct symbols")
        views = await asyncio.gather(
            *(self.history(a, days=days, interval=interval) for a in unique)
        )
        notes: list[str] = []
        merged = self._merge_provenance([v.provenance for v in views])
        usable = [v for v in views if len(v.bars) >= 2]
        for view in views:
            if len(view.bars) < 2:
                notes.append(
                    f"{view.asset.symbol}: no usable history; excluded from the comparison."
                )
        if len(usable) < 2:
            return ComparisonView(
                interval,
                (),
                (),
                {},
                merged,
                tuple(notes + ["Not enough data to compare."]),
            )
        by_time = [{b.start_at: float(b.close) for b in v.bars} for v in usable]
        common = sorted(set.intersection(*(set(m) for m in by_time)))
        if len(common) < 2:
            return ComparisonView(
                interval,
                (),
                (),
                {},
                merged,
                tuple(
                    notes
                    + [
                        "The instruments share fewer than two common bars; no comparison is possible."
                    ]
                ),
            )
        notes.append(
            f"Compared over {len(common)} common bars; bars that exist for only some instruments are ignored."
        )
        periods = PERIODS_PER_YEAR.get(interval)
        series: list[ComparisonSeries] = []
        returns_by_symbol: dict[str, list[float]] = {}
        for view, mapping in zip(usable, by_time, strict=True):
            closes = [mapping[t] for t in common]
            rets = [r for r in simple_returns(closes) if r is not None]
            returns_by_symbol[view.asset.symbol] = rets
            series.append(
                ComparisonSeries(
                    asset=view.asset,
                    indexed=tuple(100.0 * c / closes[0] for c in closes),
                    period_return=closes[-1] / closes[0] - 1.0,
                    annualized_volatility=(
                        historical_volatility(rets, periods_per_year=periods)
                        if periods and len(rets) >= 2
                        else None
                    ),
                    max_drawdown=maximum_drawdown(closes),
                )
            )
        correlations: dict[str, dict[str, float | None]] = {}
        for a in returns_by_symbol:
            correlations[a] = {}
            for b in returns_by_symbol:
                if a == b:
                    correlations[a][b] = 1.0
                    continue
                try:
                    value = pearson_correlation(returns_by_symbol[a], returns_by_symbol[b])
                    correlations[a][b] = value if math.isfinite(value) else None
                except (EngineValidationError, InsufficientDataError, FinancialCalculationError):
                    correlations[a][b] = None
        return ComparisonView(
            interval,
            tuple(common),
            tuple(series),
            correlations,
            merged,
            tuple(notes),
        )


def decimal_or_none(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))
