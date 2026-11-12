"""Financial Modeling Prep adapter, "stable" API (free key: 250 requests/day)."""

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


class FmpMarketDataProvider(HttpMarketProvider):
    name = "fmp"
    label = "Financial Modeling Prep"
    capabilities = ("quotes", "bars", "search")
    supported_intervals = ("1day",)
    default_base_url = "https://financialmodelingprep.com/stable"
    default_policy = ProviderPolicy(
        per_minute=20, per_day=250, note="Free plan: 250 requests/day; some symbols are premium."
    )

    def _auth_params(self) -> dict[str, str]:
        return {"apikey": self._api_key}

    def _inspect(self, payload: Any, *, path: str, symbol: str) -> None:
        if not isinstance(payload, dict):
            return
        message = str(payload.get("Error Message") or payload.get("message") or "")
        lowered = message.lower()
        if not lowered:
            return
        if "limit" in lowered:
            raise MarketDataRateLimitedError(message, component=self.name, operation=path)
        if "invalid api key" in lowered or "apikey" in lowered:
            raise MarketDataUnavailableError(
                "Financial Modeling Prep rejected the configured API key",
                component=self.name,
                operation=path,
                retryable=False,
            )
        if "premium" in lowered or "subscription" in lowered or "plan" in lowered:
            raise MarketDataNotEntitledError(message, component=self.name, operation=path)
        raise MarketDataUnavailableError(message, component=self.name, operation=path)

    async def get_quotes(self, assets: Sequence[AssetId]) -> Sequence[PriceQuote]:
        quotes: list[PriceQuote] = []
        for asset in assets:
            quote = await self._quote(asset)
            if quote is not None:
                quotes.append(quote)
        return tuple(quotes)

    async def _quote(self, asset: AssetId) -> PriceQuote | None:
        payload = await self._get("/quote", {"symbol": asset.symbol}, symbol=asset.symbol)
        item = payload[0] if isinstance(payload, list) and payload else None
        if not isinstance(item, Mapping):
            return None
        try:
            price = self.decimal(item.get("price"))
            observed_at = self.utc_from_epoch(item.get("timestamp"))
        except ValueError:
            return None
        try:
            previous: Decimal | None = self.decimal(item.get("previousClose"))
        except ValueError:
            previous = None
        change = self.percent_to_rate(item.get("changePercentage", item.get("changesPercentage")))
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
        if interval != "1day":
            return ()
        payload = await self._get(
            "/historical-price-eod/full",
            {
                "symbol": asset.symbol,
                "from": start_at.strftime("%Y-%m-%d"),
                "to": end_at.strftime("%Y-%m-%d"),
            },
            symbol=asset.symbol,
        )
        if isinstance(payload, Mapping):  # older response shape: {"symbol":..., "historical":[...]}
            payload = payload.get("historical")
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
                    open_=self.decimal(item.get("open")),
                    high=self.decimal(item.get("high")),
                    low=self.decimal(item.get("low")),
                    close=self.decimal(item.get("close")),
                    volume=self.decimal(item.get("volume"), default=Decimal("0")),
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
            "/search-symbol",
            {"query": term, "limit": max(1, min(limit, 25))},
            symbol=term,
            not_found_ok=True,
        )
        if not isinstance(payload, list):
            return ()
        results: list[InstrumentInfo] = []
        for item in payload:
            if not isinstance(item, Mapping) or not item.get("symbol"):
                continue
            try:
                currency = item.get("currency")
                asset = AssetId(
                    symbol=str(item["symbol"]).upper(),
                    asset_class=AssetClass.UNKNOWN,
                    exchange=str(item["exchange"]) if item.get("exchange") else None,
                    currency=currency_of(AssetId("X"), currency) if currency else None,
                )
                results.append(
                    InstrumentInfo(asset=asset, name=str(item.get("name") or item["symbol"]))
                )
            except ValueError:
                continue
        return tuple(results[:limit])
