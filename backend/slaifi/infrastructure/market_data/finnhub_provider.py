"""Finnhub adapter (free key: 60 requests/minute). Quotes and symbol search only.

Finnhub's candle (history) endpoint is a paid feature, so this adapter does not offer history.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from slaifi.core.utils.errors import MarketDataRateLimitedError, MarketDataUnavailableError
from slaifi.domain.assets import AssetClass, AssetId
from slaifi.domain.market import InstrumentInfo, PriceQuote, ProviderPolicy
from slaifi.infrastructure.market_data.bars import currency_of
from slaifi.infrastructure.market_data.base import HttpMarketProvider

_TYPE_TO_CLASS = {
    "common stock": AssetClass.EQUITY,
    "adr": AssetClass.EQUITY,
    "etp": AssetClass.ETF,
    "etf": AssetClass.ETF,
    "index": AssetClass.INDEX,
    "crypto": AssetClass.CRYPTO,
}


class FinnhubMarketDataProvider(HttpMarketProvider):
    name = "finnhub"
    label = "Finnhub"
    capabilities = ("quotes", "search")
    supported_intervals = ()
    default_base_url = "https://finnhub.io/api/v1"
    default_policy = ProviderPolicy(
        per_minute=55, note="Free plan: 60 requests/minute; quotes and search only."
    )

    def _auth_headers(self) -> dict[str, str]:
        return {"X-Finnhub-Token": self._api_key}

    def _inspect(self, payload: Any, *, path: str, symbol: str) -> None:
        if isinstance(payload, dict) and payload.get("error"):
            message = str(payload["error"])
            lowered = message.lower()
            if "limit" in lowered:
                raise MarketDataRateLimitedError(message, component=self.name, operation=path)
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
        if not isinstance(payload, Mapping):
            return None
        try:
            price = self.decimal(payload.get("c"))
            observed_at = self.utc_from_epoch(payload.get("t"))
        except ValueError:
            return None  # Finnhub answers unknown symbols with zeros
        try:
            previous: Decimal | None = self.decimal(payload.get("pc"))
        except ValueError:
            previous = None
        if previous is not None and previous <= 0:
            previous = None
        return PriceQuote(
            asset=asset,
            price=price,
            currency=currency_of(asset),
            observed_at=observed_at,
            source=self.name,
            change_rate=self.percent_to_rate(payload.get("dp")),
            previous_close=previous,
        )

    async def search_instruments(self, query: str, *, limit: int = 10) -> Sequence[InstrumentInfo]:
        term = query.strip()
        if not term:
            return ()
        payload = await self._get("/search", {"q": term}, symbol=term, not_found_ok=True)
        rows = payload.get("result") if isinstance(payload, Mapping) else None
        if not isinstance(rows, list):
            return ()
        results: list[InstrumentInfo] = []
        for item in rows:
            if not isinstance(item, Mapping) or not item.get("symbol"):
                continue
            kind = str(item.get("type") or "")
            try:
                results.append(
                    InstrumentInfo(
                        asset=AssetId(
                            symbol=str(item["symbol"]).upper(),
                            asset_class=_TYPE_TO_CLASS.get(kind.lower(), AssetClass.UNKNOWN),
                        ),
                        name=str(item.get("description") or item["symbol"]),
                        instrument_type=kind or None,
                    )
                )
            except ValueError:
                continue
        return tuple(results[:limit])
