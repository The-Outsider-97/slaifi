"""In-process last-known cache (used when no durable cache is available, and in tests)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from slaifi.domain.assets import AssetId
from slaifi.domain.market import InstrumentInfo, OHLCVBar, PriceQuote
from slaifi.infrastructure.market_data import cache_codec as cc


class InMemoryMarketCache:
    def __init__(self) -> None:
        self._quotes: dict[str, tuple[PriceQuote, datetime]] = {}
        self._bars: dict[tuple[str, str, str], tuple[dict[datetime, OHLCVBar], datetime]] = {}
        self._search: dict[str, tuple[tuple[InstrumentInfo, ...], str, datetime]] = {}

    def save_quote(self, quote: PriceQuote, *, saved_at: datetime) -> None:
        k = cc.key(quote.asset)
        old = self._quotes.get(k)
        if old is None or quote.observed_at >= old[0].observed_at:
            self._quotes[k] = (quote, saved_at)

    def load_quote(self, asset: AssetId) -> tuple[PriceQuote, datetime] | None:
        return self._quotes.get(cc.key(asset))

    def save_bars(
        self,
        asset: AssetId,
        interval: str,
        bars: Sequence[OHLCVBar],
        *,
        source: str,
        saved_at: datetime,
    ) -> None:
        slot = self._bars.setdefault((cc.key(asset), interval, source), ({}, saved_at))
        slot[0].update({b.start_at: b for b in bars})
        self._bars[(cc.key(asset), interval, source)] = (slot[0], saved_at)

    def load_bars(
        self, asset: AssetId, interval: str, *, start_at: datetime, end_at: datetime
    ) -> tuple[tuple[OHLCVBar, ...], str | None, datetime | None]:
        best: tuple[tuple[OHLCVBar, ...], str, datetime] | None = None
        for (k, iv, source), (rows, saved) in self._bars.items():
            if k != cc.key(asset) or iv != interval:
                continue
            inside = tuple(
                sorted(
                    (b for b in rows.values() if start_at <= b.start_at <= end_at),
                    key=lambda b: b.start_at,
                )
            )
            if inside and (best is None or (len(inside), saved) > (len(best[0]), best[2])):
                best = (inside, source, saved)
        if best is None:
            return (), None, None
        return best[0], best[1], best[2]

    def save_search(
        self, query: str, results: Sequence[InstrumentInfo], *, source: str, saved_at: datetime
    ) -> None:
        self._search[query.strip().lower()] = (tuple(results), source, saved_at)

    def load_search(self, query: str) -> tuple[tuple[InstrumentInfo, ...], str, datetime] | None:
        return self._search.get(query.strip().lower())
