"""Market-data application service: search, quotes, history, statistics and comparison.

Every result carries :class:`DataProvenance`, so callers (and the UI) can always tell mock from
live, delayed from real-time, and how old an observation is. Nothing is interpolated or invented:
if the provider has no data the result says so.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from statistics import mean

from slaifi.core.utils.errors import SymbolNotFoundError, ValidationError
from slaifi.domain.assets import AssetClass, AssetId
from slaifi.domain.market import InstrumentInfo, MarketDataProvider, OHLCVBar, PriceQuote
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


@dataclass(frozen=True, slots=True)
class DataProvenance:
    mode: str  # live | delayed | live_delay_unknown | mock
    source: str
    observed_at: datetime | None
    retrieved_at: datetime
    age_seconds: float | None
    illustrative: bool
    delayed: bool | None
    market_open: bool | None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class QuoteView:
    quote: PriceQuote
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


class MarketDataService:
    """Facade over a :class:`MarketDataProvider` adding provenance, validation and statistics."""

    def __init__(
        self,
        provider: MarketDataProvider,
        *,
        clock: Callable[[], datetime] = _utc_now,
        max_bars: int = 5000,
    ) -> None:
        self._provider = provider
        self._clock = clock
        self._max_bars = max_bars
        self._resolved: dict[tuple[str, str | None, str | None], AssetId] = {}

    @property
    def supported_intervals(self) -> tuple[str, ...]:
        """Intervals the active provider can actually serve (never more than the API accepts)."""

        offered = getattr(self._provider, "supported_intervals", None)
        if not offered:
            return VALID_INTERVALS
        return tuple(i for i in VALID_INTERVALS if i in offered)

    # ------------------------------------------------------------------ provenance
    @property
    def data_mode(self) -> str:
        return str(getattr(self._provider, "data_mode", "unknown"))

    def provenance(
        self,
        *,
        observed_at: datetime | None = None,
        market_open: bool | None = None,
        delayed: bool | None = None,
        illustrative: bool | None = None,
        notes: Sequence[str] = (),
    ) -> DataProvenance:
        now = self._clock()
        mode = self.data_mode
        is_illustrative = bool(illustrative) if illustrative is not None else mode == "mock"
        if mode == "mock" or is_illustrative:
            label = "mock"
        elif delayed is True:
            label = "delayed"
        elif delayed is False:
            label = "live"
        else:
            label = "live_delay_unknown"
        collected = list(notes)
        if label == "mock":
            collected.append("Illustrative demonstration data, not market data.")
        elif label == "delayed":
            collected.append("Quotes from this feed are delayed.")
        elif label == "live_delay_unknown":
            collected.append("The feed's delay is not known; do not assume real-time prices.")
        if market_open is False:
            collected.append("The market is closed: the price is the last observation.")
        return DataProvenance(
            mode=label,
            source="mock" if mode == "mock" else str(getattr(self._provider, "source_name", mode)),
            observed_at=observed_at,
            retrieved_at=now,
            age_seconds=max(0.0, (now - observed_at).total_seconds()) if observed_at else None,
            illustrative=is_illustrative,
            delayed=delayed,
            market_open=market_open,
            notes=tuple(collected),
        )

    def _quote_provenance(self, quote: PriceQuote) -> DataProvenance:
        return self.provenance(
            observed_at=quote.observed_at,
            market_open=quote.is_market_open,
            delayed=quote.delayed,
            illustrative=quote.illustrative,
        )

    # ------------------------------------------------------------------ search & resolution
    async def search(self, query: str, *, limit: int = 10) -> SearchView:
        text = query.strip()
        if not text:
            raise ValidationError("search query must not be empty")
        if len(text) > 64:
            raise ValidationError("search query is too long")
        search = getattr(self._provider, "search_instruments", None)
        if search is None:
            return SearchView(
                text, (), self.provenance(notes=("This provider does not support search.",)), False
            )
        results = tuple(await search(text, limit=max(1, min(limit, 25))))
        return SearchView(text, results, self.provenance(), True)

    async def resolve_asset(
        self,
        symbol: str,
        *,
        exchange: str | None = None,
        asset_class: AssetClass | None = None,
    ) -> AssetId:
        """Return a fully identified asset (class, exchange, currency) for a user-supplied symbol."""

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
        search = getattr(self._provider, "search_instruments", None)
        if search is not None:
            try:
                hits = await search(text, limit=10)
            except Exception:  # noqa: BLE001 - resolution is best-effort; quote errors surface later
                hits = ()
            exact = [h for h in hits if h.asset.symbol == text]
            if exchange:
                exact = [h for h in exact if (h.asset.exchange or "").upper() == exchange.upper()]
            if asset_class and asset_class is not AssetClass.UNKNOWN:
                exact = [h for h in exact if h.asset.asset_class is asset_class]
            if exact:
                found = exact[0].asset
        if found is None:
            if getattr(self._provider, "strict_catalog", False) or self.data_mode == "mock":
                raise SymbolNotFoundError(f"{text} is not in the illustrative demo catalogue")
            found = AssetId(
                text, asset_class or AssetClass.UNKNOWN, exchange.upper() if exchange else None
            )
        self._resolved[key] = found
        return found

    # ------------------------------------------------------------------ quotes
    async def quote(self, asset: AssetId) -> QuoteView | None:
        quotes = await self._provider.get_quotes([asset])
        if not quotes:
            return None
        quote = quotes[0]
        return QuoteView(quote, self._quote_provenance(quote))

    async def quotes(self, assets: Sequence[AssetId]) -> list[QuoteView]:
        if not assets:
            return []
        result = await self._provider.get_quotes(list(assets))
        return [QuoteView(q, self._quote_provenance(q)) for q in result]

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
        raw = tuple(
            await self._provider.get_bars(asset, start_at=start, end_at=end, interval=interval)
        )
        bars, duplicates, reordered = normalize_bars(raw)
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
                f"{interval} bars are not available from this data source; it provides: {', '.join(self.supported_intervals)}."
            )
        elif not bars:
            notes.append("No historical data is available for this instrument and range.")
        elif quality.gap_count:
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
        last_quote_time = bars[-1].end_at if bars else None
        return HistoryView(
            asset=asset,
            interval=interval,
            bars=bars,
            quality=quality,
            provenance=self.provenance(observed_at=last_quote_time),
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
                self.provenance(),
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
                self.provenance(),
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
            self.provenance(observed_at=common[-1]),
            tuple(notes),
        )


def decimal_or_none(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))
