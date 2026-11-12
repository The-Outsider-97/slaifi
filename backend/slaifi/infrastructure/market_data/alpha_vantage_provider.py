"""Alpha Vantage adapter (free key: 25 requests/day, 5/minute).

Free-plan limits shape this adapter: GLOBAL_QUOTE is end-of-day (so its quotes are flagged
delayed and carry the trading *date* as the observation time), daily history is the latest ~100
trading days, weekly and monthly history cover many years, and intraday history is premium.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from slaifi.core.utils.errors import (
    MarketDataNotEntitledError,
    MarketDataRateLimitedError,
    MarketDataUnavailableError,
    SymbolNotFoundError,
)
from slaifi.domain.assets import AssetClass, AssetId
from slaifi.domain.market import InstrumentInfo, OHLCVBar, PriceQuote, ProviderPolicy
from slaifi.infrastructure.market_data.bars import currency_of, make_bar, within
from slaifi.infrastructure.market_data.base import HttpMarketProvider

_SERIES = {
    "1day": ("TIME_SERIES_DAILY", "Time Series (Daily)"),
    "1week": ("TIME_SERIES_WEEKLY", "Weekly Time Series"),
    "1month": ("TIME_SERIES_MONTHLY", "Monthly Time Series"),
}
_TYPE_TO_CLASS = {"equity": AssetClass.EQUITY, "etf": AssetClass.ETF}


class AlphaVantageMarketDataProvider(HttpMarketProvider):
    name = "alphavantage"
    label = "Alpha Vantage"
    capabilities = ("quotes", "bars", "search")
    supported_intervals = ("1day", "1week", "1month")
    quotes_delayed = True  # free GLOBAL_QUOTE updates at the end of each trading day
    default_base_url = "https://www.alphavantage.co"
    default_policy = ProviderPolicy(
        per_minute=5,
        per_day=25,
        note="Free plan: 25 requests/day; end-of-day quotes; daily history limited to ~100 days.",
    )

    def _auth_params(self) -> dict[str, str]:
        return {"apikey": self._api_key}

    def _inspect(self, payload: Any, *, path: str, symbol: str) -> None:
        if not isinstance(payload, dict):
            return
        note = payload.get("Note") or payload.get("Information")
        if note:
            text = str(note)
            lowered = text.lower()
            if "apikey" in lowered and ("invalid" in lowered or "missing" in lowered):
                raise MarketDataUnavailableError(
                    "Alpha Vantage rejected the configured API key",
                    component=self.name,
                    operation=path,
                    retryable=False,
                )
            if "premium" in lowered and "rate limit" not in lowered and "per day" not in lowered:
                raise MarketDataNotEntitledError(text, component=self.name, operation=path)
            raise MarketDataRateLimitedError(text, component=self.name, operation=path)
        if payload.get("Error Message"):
            raise SymbolNotFoundError(
                f"{symbol}: {payload['Error Message']}", component=self.name, operation=path
            )

    async def get_quotes(self, assets: Sequence[AssetId]) -> Sequence[PriceQuote]:
        quotes: list[PriceQuote] = []
        for asset in assets:
            quote = await self._quote(asset)
            if quote is not None:
                quotes.append(quote)
        return tuple(quotes)

    async def _quote(self, asset: AssetId) -> PriceQuote | None:
        payload = await self._get(
            "/query", {"function": "GLOBAL_QUOTE", "symbol": asset.symbol}, symbol=asset.symbol
        )
        item = payload.get("Global Quote") if isinstance(payload, Mapping) else None
        if not isinstance(item, Mapping) or not item:
            return None
        try:
            price = self.decimal(item.get("05. price"))
            observed_at = self.utc_from_text(item.get("07. latest trading day"))
        except ValueError:
            return None
        try:
            previous: Decimal | None = self.decimal(item.get("08. previous close"))
        except ValueError:
            previous = None
        return PriceQuote(
            asset=asset,
            price=price,
            currency=currency_of(asset),
            observed_at=observed_at,
            source=self.name,
            change_rate=self.percent_to_rate(item.get("10. change percent")),
            delayed=True,
            previous_close=previous,
        )

    async def get_bars(
        self, asset: AssetId, *, start_at: datetime, end_at: datetime, interval: str = "1day"
    ) -> Sequence[OHLCVBar]:
        spec = _SERIES.get(interval)
        if spec is None:
            return ()
        function, key = spec
        params: dict[str, str | int] = {"function": function, "symbol": asset.symbol}
        payload = await self._get("/query", params, symbol=asset.symbol)
        series = payload.get(key) if isinstance(payload, Mapping) else None
        if not isinstance(series, Mapping):
            return ()
        bars: list[OHLCVBar] = []
        for day, item in series.items():
            if not isinstance(item, Mapping):
                continue
            try:
                bar = make_bar(
                    asset,
                    self.utc_from_text(day).astimezone(UTC),
                    interval,
                    open_=self.decimal(item.get("1. open")),
                    high=self.decimal(item.get("2. high")),
                    low=self.decimal(item.get("3. low")),
                    close=self.decimal(item.get("4. close")),
                    volume=self.decimal(item.get("5. volume"), default=Decimal("0")),
                )
            except ValueError:
                continue
            if bar is not None:
                bars.append(bar)
        return within(bars, start_at, end_at)

    async def search_instruments(self, query: str, *, limit: int = 10) -> Sequence[InstrumentInfo]:
        term = query.strip()
        if not term:
            return ()
        payload = await self._get(
            "/query",
            {"function": "SYMBOL_SEARCH", "keywords": term},
            symbol=term,
            not_found_ok=True,
        )
        rows = payload.get("bestMatches") if isinstance(payload, Mapping) else None
        if not isinstance(rows, list):
            return ()
        results: list[InstrumentInfo] = []
        for item in rows:
            if not isinstance(item, Mapping) or not item.get("1. symbol"):
                continue
            kind = str(item.get("3. type") or "")
            try:
                currency = item.get("8. currency")
                symbol = str(item["1. symbol"]).upper()
                results.append(
                    InstrumentInfo(
                        asset=AssetId(
                            symbol=symbol,
                            asset_class=_TYPE_TO_CLASS.get(kind.lower(), AssetClass.UNKNOWN),
                            currency=currency_of(AssetId(symbol), currency) if currency else None,
                        ),
                        name=str(item.get("2. name") or symbol),
                        country=str(item["4. region"]) if item.get("4. region") else None,
                        instrument_type=kind or None,
                    )
                )
            except ValueError:
                continue
        return tuple(results[:limit])
