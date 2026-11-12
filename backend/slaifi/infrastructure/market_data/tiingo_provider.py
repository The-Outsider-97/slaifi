"""Tiingo adapter (free key: about 50 requests/hour, 1000/day).

Quotes come from Tiingo's IEX endpoint (US-listed instruments), history from its end-of-day
endpoint. History uses the split- and dividend-adjusted OHLCV fields so returns and
volatility are not distorted by corporate actions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from slaifi.core.utils.errors import (
    MarketDataNotEntitledError,
    MarketDataRateLimitedError,
    MarketDataUnavailableError,
)
from slaifi.domain.assets import AssetClass, AssetId
from slaifi.domain.market import InstrumentInfo, OHLCVBar, PriceQuote, ProviderPolicy
from slaifi.infrastructure.market_data.bars import currency_of, make_bar, within
from slaifi.infrastructure.market_data.base import HttpMarketProvider

_RESAMPLE = {"1day": "daily", "1week": "weekly", "1month": "monthly"}
_TYPE_TO_CLASS = {"stock": AssetClass.EQUITY, "etf": AssetClass.ETF}


class TiingoMarketDataProvider(HttpMarketProvider):
    name = "tiingo"
    label = "Tiingo"
    capabilities = ("quotes", "bars", "search")
    supported_intervals = ("1day", "1week", "1month")
    default_base_url = "https://api.tiingo.com"
    default_policy = ProviderPolicy(
        per_hour=50,
        per_day=1000,
        note="Free plan: about 50 requests/hour, 1000/day, 500 distinct symbols/month.",
    )

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Token {self._api_key}"}

    def _inspect(self, payload: Any, *, path: str, symbol: str) -> None:
        if not isinstance(payload, dict):
            return
        detail = str(payload.get("detail") or payload.get("message") or "")
        lowered = detail.lower()
        if not lowered:
            return
        if "exceeded" in lowered or "allocation" in lowered or "rate" in lowered:
            raise MarketDataRateLimitedError(detail, component=self.name, operation=path)
        if "token" in lowered and ("invalid" in lowered or "authenticat" in lowered):
            raise MarketDataUnavailableError(
                "Tiingo rejected the configured API key",
                component=self.name,
                operation=path,
                retryable=False,
            )
        if "permission" in lowered or "subscription" in lowered or "not included" in lowered:
            raise MarketDataNotEntitledError(detail, component=self.name, operation=path)
        raise MarketDataUnavailableError(detail, component=self.name, operation=path)

    async def get_quotes(self, assets: Sequence[AssetId]) -> Sequence[PriceQuote]:
        quotes: list[PriceQuote] = []
        for asset in assets:
            quote = await self._quote(asset)
            if quote is not None:
                quotes.append(quote)
        return tuple(quotes)

    async def _quote(self, asset: AssetId) -> PriceQuote | None:
        payload = await self._get(f"/iex/{asset.symbol.lower()}", {}, symbol=asset.symbol)
        item = payload[0] if isinstance(payload, list) and payload else None
        if not isinstance(item, Mapping):
            return None
        try:
            price = self.decimal(
                item.get("tngoLast") if item.get("tngoLast") is not None else item.get("last")
            )
            observed_at = self.utc_from_text(item.get("lastSaleTimestamp") or item.get("timestamp"))
        except ValueError:
            return None
        try:
            previous: Decimal | None = self.decimal(item.get("prevClose"))
        except ValueError:
            previous = None
        change = float(price / previous - 1) if previous else None
        return PriceQuote(
            asset=asset,
            price=price,
            currency=currency_of(asset),
            observed_at=observed_at,
            source=self.name,
            change_rate=change,
            previous_close=previous,
        )

    async def get_bars(
        self, asset: AssetId, *, start_at: datetime, end_at: datetime, interval: str = "1day"
    ) -> Sequence[OHLCVBar]:
        resample = _RESAMPLE.get(interval)
        if resample is None:
            return ()
        payload = await self._get(
            f"/tiingo/daily/{asset.symbol.lower()}/prices",
            {
                "startDate": start_at.strftime("%Y-%m-%d"),
                "endDate": end_at.strftime("%Y-%m-%d"),
                "resampleFreq": resample,
            },
            symbol=asset.symbol,
        )
        if not isinstance(payload, list):
            return ()
        bars: list[OHLCVBar] = []
        for item in payload:
            if not isinstance(item, Mapping):
                continue
            try:
                bar = make_bar(
                    asset,
                    self.utc_from_text(item.get("date")),
                    interval,
                    open_=self.decimal(item.get("adjOpen", item.get("open"))),
                    high=self.decimal(item.get("adjHigh", item.get("high"))),
                    low=self.decimal(item.get("adjLow", item.get("low"))),
                    close=self.decimal(item.get("adjClose", item.get("close"))),
                    volume=self.decimal(
                        item.get("adjVolume", item.get("volume")), default=Decimal("0")
                    ),
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
            "/tiingo/utilities/search",
            {"query": term, "limit": max(1, min(limit, 25))},
            symbol=term,
            not_found_ok=True,
        )
        if not isinstance(payload, list):
            return ()
        results: list[InstrumentInfo] = []
        for item in payload:
            if not isinstance(item, Mapping) or not item.get("ticker"):
                continue
            if item.get("isActive") is False:
                continue
            kind = str(item.get("assetType") or "")
            try:
                results.append(
                    InstrumentInfo(
                        asset=AssetId(
                            symbol=str(item["ticker"]).upper(),
                            asset_class=_TYPE_TO_CLASS.get(kind.lower(), AssetClass.UNKNOWN),
                        ),
                        name=str(item.get("name") or item["ticker"]),
                        country=str(item["countryCode"]) if item.get("countryCode") else None,
                        instrument_type=kind or None,
                    )
                )
            except ValueError:
                continue
        return tuple(results[:limit])
