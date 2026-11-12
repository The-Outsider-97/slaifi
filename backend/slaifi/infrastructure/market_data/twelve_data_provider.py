"""Twelve Data adapter (free "Basic" key: about 8 requests/minute and 800/day)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from slaifi.core.utils.errors import (
    MarketDataNotEntitledError,
    MarketDataRateLimitedError,
    MarketDataUnavailableError,
    SymbolNotFoundError,
    ValidationError,
)
from slaifi.domain.assets import AssetClass, AssetId
from slaifi.domain.market import InstrumentInfo, OHLCVBar, PriceQuote, ProviderPolicy
from slaifi.infrastructure.market_data.bars import STEPS, currency_of, make_bar
from slaifi.infrastructure.market_data.base import HttpMarketProvider

SUPPORTED_INTERVALS: dict[str, timedelta] = dict(STEPS)
_MAX_OUTPUT = 5000
_TYPE_TO_CLASS = {
    "common stock": AssetClass.EQUITY,
    "equity": AssetClass.EQUITY,
    "etf": AssetClass.ETF,
    "index": AssetClass.INDEX,
    "digital currency": AssetClass.CRYPTO,
    "physical currency": AssetClass.FOREX,
    "bond": AssetClass.BOND,
    "commodity": AssetClass.COMMODITY,
}


class TwelveDataMarketDataProvider(HttpMarketProvider):
    """Translate Twelve Data responses into provider-neutral SLAIFI objects."""

    name = "twelvedata"
    label = "Twelve Data"
    capabilities = ("quotes", "bars", "search")
    supported_intervals = tuple(SUPPORTED_INTERVALS)
    default_base_url = "https://api.twelvedata.com"
    default_policy = ProviderPolicy(
        per_minute=8, per_day=800, note="Free Basic plan: 8 requests/minute, 800/day."
    )

    def __init__(self, *, data_delay_minutes: int | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._delay = data_delay_minutes

    def _auth_params(self) -> dict[str, str]:
        return {"apikey": self._api_key}

    def _inspect(self, payload: Any, *, path: str, symbol: str) -> None:
        if not isinstance(payload, dict) or payload.get("status") != "error":
            return
        code = payload.get("code")
        message = str(payload.get("message") or "market provider error")
        lowered = message.lower()
        if code == 429 or "api credits" in lowered or "rate limit" in lowered:
            raise MarketDataRateLimitedError(message, component=self.name, operation=path)
        if "plan" in lowered or "upgrade" in lowered or code == 402:
            raise MarketDataNotEntitledError(message, component=self.name, operation=path)
        if code in (401, 403) or "apikey" in lowered or "api key" in lowered:
            raise MarketDataUnavailableError(
                "Twelve Data rejected the configured API key",
                component=self.name,
                operation=path,
                retryable=False,
            )
        if code in (400, 404):
            raise SymbolNotFoundError(f"{symbol}: {message}", component=self.name, operation=path)
        raise MarketDataUnavailableError(message, component=self.name, operation=path)

    async def get_quotes(self, assets: Sequence[AssetId]) -> Sequence[PriceQuote]:
        return tuple([await self._quote(a) for a in assets])

    async def _quote(self, asset: AssetId) -> PriceQuote:
        params: dict[str, str | int] = {"symbol": asset.symbol}
        if asset.exchange:
            params["exchange"] = asset.exchange
        payload = await self._get("/quote", params, symbol=asset.symbol)
        try:
            price = self.decimal(payload.get("close"))
        except ValueError as exc:
            raise MarketDataUnavailableError(
                f"Twelve Data returned no usable price for {asset.symbol}", component=self.name
            ) from exc
        stamp = payload.get("last_quote_at") or payload.get("timestamp")
        try:
            observed_at = self.utc_from_epoch(stamp)
        except ValueError as exc:
            raise MarketDataUnavailableError(
                f"Twelve Data returned no observation time for {asset.symbol}", component=self.name
            ) from exc
        try:
            previous = self.decimal(payload.get("previous_close"))
        except ValueError:
            previous = None
        is_open = payload.get("is_market_open")
        return PriceQuote(
            asset=asset,
            price=price,
            currency=currency_of(asset, payload.get("currency")),
            observed_at=observed_at,
            source=self.name,
            change_rate=self.percent_to_rate(payload.get("percent_change")),
            is_market_open=is_open if isinstance(is_open, bool) else None,
            delayed=None if self._delay is None else self._delay > 0,
            previous_close=previous,
        )

    async def get_bars(
        self, asset: AssetId, *, start_at: datetime, end_at: datetime, interval: str = "1day"
    ) -> Sequence[OHLCVBar]:
        if end_at <= start_at:
            raise ValueError("end_at must be later than start_at")
        step = SUPPORTED_INTERVALS.get(interval)
        if step is None:
            raise ValidationError(f"unsupported interval {interval!r}")
        fmt = "%Y-%m-%d %H:%M:%S" if step < timedelta(days=1) else "%Y-%m-%d"
        params: dict[str, str | int] = {
            "symbol": asset.symbol,
            "interval": interval,
            "start_date": start_at.astimezone(UTC).strftime(fmt),
            "end_date": end_at.astimezone(UTC).strftime(fmt),
            "order": "ASC",
            "timezone": "UTC",
            "outputsize": _MAX_OUTPUT,
        }
        if asset.exchange:
            params["exchange"] = asset.exchange
        payload = await self._get("/time_series", params, symbol=asset.symbol)
        values = payload.get("values") if isinstance(payload, dict) else None
        if not isinstance(values, list):
            return ()
        bars: list[OHLCVBar] = []
        for item in values:
            if not isinstance(item, Mapping):
                continue
            try:
                bar = make_bar(
                    asset,
                    self.utc_from_text(item.get("datetime")),
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
        return tuple(sorted(bars, key=lambda b: b.start_at))

    async def search_instruments(self, query: str, *, limit: int = 10) -> Sequence[InstrumentInfo]:
        term = query.strip()
        if not term:
            return ()
        payload = await self._get(
            "/symbol_search",
            {"symbol": term, "outputsize": max(1, min(limit, 30))},
            symbol=term,
            not_found_ok=True,
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            return ()
        results: list[InstrumentInfo] = []
        for item in data:
            if not isinstance(item, Mapping) or not item.get("symbol"):
                continue
            kind = str(item.get("instrument_type") or "")
            try:
                asset = AssetId(
                    symbol=str(item["symbol"]),
                    asset_class=_TYPE_TO_CLASS.get(kind.lower(), AssetClass.UNKNOWN),
                    exchange=str(item["exchange"]) if item.get("exchange") else None,
                    currency=currency_of(AssetId(str(item["symbol"])), item.get("currency"))
                    if item.get("currency")
                    else None,
                )
                results.append(
                    InstrumentInfo(
                        asset=asset,
                        name=str(item.get("instrument_name") or item["symbol"]),
                        country=str(item["country"]) if item.get("country") else None,
                        instrument_type=kind or None,
                    )
                )
            except ValueError:
                continue
        return tuple(results[:limit])


__all__ = ["SUPPORTED_INTERVALS", "TwelveDataMarketDataProvider"]
