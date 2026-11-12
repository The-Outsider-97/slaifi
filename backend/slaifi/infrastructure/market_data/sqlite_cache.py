"""Durable last-known market cache on SLAI's shared ``Database`` tool.

Only real observations returned by providers are stored. The cache lives in its own file, so it
can be deleted at any time without touching the paper-trading ledger.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from applications.tools.database import Database, Migration

from slaifi.domain.assets import AssetId
from slaifi.domain.market import InstrumentInfo, OHLCVBar, PriceQuote
from slaifi.infrastructure.market_data import cache_codec as cc

_V1 = (
    """CREATE TABLE quotes (
        symbol TEXT PRIMARY KEY,
        observed_at TEXT NOT NULL,
        saved_at TEXT NOT NULL,
        payload TEXT NOT NULL
    )""",
    """CREATE TABLE bars (
        symbol TEXT NOT NULL,
        interval TEXT NOT NULL,
        source TEXT NOT NULL,
        start_at TEXT NOT NULL,
        end_at TEXT NOT NULL,
        open TEXT NOT NULL,
        high TEXT NOT NULL,
        low TEXT NOT NULL,
        close TEXT NOT NULL,
        volume TEXT NOT NULL,
        saved_at TEXT NOT NULL,
        asset_json TEXT NOT NULL,
        PRIMARY KEY (symbol, interval, source, start_at)
    )""",
    """CREATE TABLE searches (
        query TEXT PRIMARY KEY,
        source TEXT NOT NULL,
        saved_at TEXT NOT NULL,
        payload TEXT NOT NULL
    )""",
)
MIGRATIONS: tuple[Migration, ...] = (Migration(1, "market last-known cache", _V1),)


class SqliteMarketCache:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._db = Database(self.path, MIGRATIONS)

    def close(self) -> None:
        self._db.close()

    # ------------------------------------------------------------------ quotes
    def save_quote(self, quote: PriceQuote, *, saved_at: datetime) -> None:
        self._db.execute(
            "INSERT INTO quotes (symbol, observed_at, saved_at, payload) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(symbol) DO UPDATE SET observed_at = excluded.observed_at,"
            " saved_at = excluded.saved_at, payload = excluded.payload"
            " WHERE excluded.observed_at >= quotes.observed_at",
            (
                cc.key(quote.asset),
                cc.utc_text(quote.observed_at),
                cc.utc_text(saved_at),
                json.dumps(cc.quote_dict(quote)),
            ),
        )

    def load_quote(self, asset: AssetId) -> tuple[PriceQuote, datetime] | None:
        row = self._db.row(
            "SELECT payload, saved_at FROM quotes WHERE symbol = ?", (cc.key(asset),)
        )
        if row is None:
            return None
        return cc.quote_from(json.loads(row["payload"])), cc.from_text(row["saved_at"])

    # ------------------------------------------------------------------ bars
    def save_bars(
        self,
        asset: AssetId,
        interval: str,
        bars: Sequence[OHLCVBar],
        *,
        source: str,
        saved_at: datetime,
    ) -> None:
        if not bars:
            return
        asset_json = json.dumps(cc.asset_dict(asset))
        stamp = cc.utc_text(saved_at)
        with self._db.transaction() as tx:
            for b in bars:
                tx.execute(
                    "INSERT INTO bars (symbol, interval, source, start_at, end_at, open, high, low,"
                    " close, volume, saved_at, asset_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
                    " ON CONFLICT(symbol, interval, source, start_at) DO UPDATE SET"
                    " end_at = excluded.end_at, open = excluded.open, high = excluded.high,"
                    " low = excluded.low, close = excluded.close, volume = excluded.volume,"
                    " saved_at = excluded.saved_at",
                    (
                        cc.key(asset),
                        interval,
                        source,
                        cc.utc_text(b.start_at),
                        cc.utc_text(b.end_at),
                        format(b.open, "f"),
                        format(b.high, "f"),
                        format(b.low, "f"),
                        format(b.close, "f"),
                        format(b.volume, "f"),
                        stamp,
                        asset_json,
                    ),
                )

    def load_bars(
        self, asset: AssetId, interval: str, *, start_at: datetime, end_at: datetime
    ) -> tuple[tuple[OHLCVBar, ...], str | None, datetime | None]:
        # One source only: mixing providers would join differently adjusted price series.
        pick = self._db.row(
            "SELECT source, COUNT(*) AS n, MAX(saved_at) AS saved FROM bars"
            " WHERE symbol = ? AND interval = ? AND start_at >= ? AND start_at <= ?"
            " GROUP BY source ORDER BY n DESC, saved DESC LIMIT 1",
            (cc.key(asset), interval, cc.utc_text(start_at), cc.utc_text(end_at)),
        )
        if pick is None:
            return (), None, None
        rows = self._db.rows(
            "SELECT * FROM bars WHERE symbol = ? AND interval = ? AND source = ?"
            " AND start_at >= ? AND start_at <= ? ORDER BY start_at",
            (cc.key(asset), interval, pick["source"], cc.utc_text(start_at), cc.utc_text(end_at)),
        )
        bars = tuple(self._bar(asset, r) for r in rows)
        return bars, str(pick["source"]), cc.from_text(pick["saved"])

    @staticmethod
    def _bar(asset: AssetId, r: dict[str, Any]) -> OHLCVBar:
        return OHLCVBar(
            asset=asset,
            start_at=cc.from_text(r["start_at"]),
            end_at=cc.from_text(r["end_at"]),
            open=Decimal(r["open"]),
            high=Decimal(r["high"]),
            low=Decimal(r["low"]),
            close=Decimal(r["close"]),
            volume=Decimal(r["volume"]),
        )

    # ------------------------------------------------------------------ search
    def save_search(
        self, query: str, results: Sequence[InstrumentInfo], *, source: str, saved_at: datetime
    ) -> None:
        self._db.execute(
            "INSERT INTO searches (query, source, saved_at, payload) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(query) DO UPDATE SET source = excluded.source,"
            " saved_at = excluded.saved_at, payload = excluded.payload",
            (
                query.strip().lower(),
                source,
                cc.utc_text(saved_at),
                json.dumps([cc.instrument_dict(i) for i in results]),
            ),
        )

    def load_search(self, query: str) -> tuple[tuple[InstrumentInfo, ...], str, datetime] | None:
        row = self._db.row(
            "SELECT payload, source, saved_at FROM searches WHERE query = ?",
            (query.strip().lower(),),
        )
        if row is None:
            return None
        items = tuple(cc.instrument_from(d) for d in json.loads(row["payload"]))
        return items, str(row["source"]), cc.from_text(row["saved_at"])
